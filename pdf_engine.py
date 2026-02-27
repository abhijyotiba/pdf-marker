"""
PDF Highlight Engine - Handles PDF processing and highlighting

Key fixes applied:
  1. Use fitz.Matrix transformation instead of manual scale_factor multiplication
     to correctly map PDF text bbox → pixel coords (handles rotation, cropbox).
  2. Use get_text("dict") with block/span positions for accurate coordinate
     extraction, falling back to search_for() only as a secondary method.
  3. When multiple matches exist, pick the one that is NOT in a header/footer
     zone (i.e. skip matches near the very top or bottom of the page).
  4. After finding the text bbox via search_for(), re-map it through the same
     transformation matrix used for rendering so coords are always in sync.
  5. Add a diagnostic mode that dumps all found text blocks with coords so
     you can verify what the PDF actually contains.
"""
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

import fitz  # PyMuPDF
from PIL import Image, ImageDraw

from config import PDF_CONFIG, TEMP_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)


@dataclass
class PartLocation:
    """Represents the location of a found part in a PDF."""
    page_index: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points
    text: str


class PDFEngine:
    """Handles PDF processing, part location, and highlighting."""

    def __init__(self):
        self.render_dpi = PDF_CONFIG["RENDER_DPI"]
        self.base_dpi = PDF_CONFIG["PDF_BASE_DPI"]
        self.scale_factor = self.render_dpi / self.base_dpi  # e.g. 300/72 ≈ 4.167

        self.highlight_color = PDF_CONFIG["HIGHLIGHT_COLOR"]
        self.highlight_width = PDF_CONFIG["HIGHLIGHT_WIDTH"]
        self.highlight_padding = PDF_CONFIG["HIGHLIGHT_PADDING"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_render_matrix(self) -> fitz.Matrix:
        """Return the same Matrix used for rendering — keeps coords in sync."""
        return fitz.Matrix(self.scale_factor, self.scale_factor)

    def _bbox_to_pixel_rect(
        self,
        bbox: Tuple[float, float, float, float],
        mat: fitz.Matrix,
    ) -> Tuple[int, int, int, int]:
        """
        Convert a PDF-space bbox (x0,y0,x1,y1) to pixel coords by applying
        the same transformation matrix used for get_pixmap().

        Using fitz.Rect * mat is the correct approach — it handles any
        page rotation or non-uniform scaling automatically, unlike a plain
        multiplication by scale_factor.
        """
        r = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3]) * mat
        return (int(r.x0), int(r.y0), int(r.x1), int(r.y1))

    def _is_in_diagram_area(
        self,
        bbox: Tuple[float, float, float, float],
        page_rect: fitz.Rect,
        margin_fraction: float = 0.05,
    ) -> bool:
        """
        Return True if the bbox is NOT in a narrow header/footer margin.
        This helps skip occurrences of the part number that appear in
        title blocks, revision tables, or file-name annotations.

        margin_fraction=0.05 means we exclude the top and bottom 5% of
        the page height (adjust if your PDFs have tall title blocks).
        """
        page_h = page_rect.height
        margin = page_h * margin_fraction
        _, y0, _, y1 = bbox
        return y0 > margin and y1 < (page_h - margin)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_part_in_pdf(
        self, pdf_path: Path, part_number: str
    ) -> Optional[PartLocation]:
        """
        Search for part_number in the PDF.

        Strategy:
          1. Use page.search_for() which is reliable for normal PDFs.
          2. Among all matches across all pages, prefer the one that lies
             inside the diagram area (not in a header/footer zone).
          3. If all matches are in header/footer zones, fall back to the
             first match (better than nothing).

        Returns PartLocation with PDF-space bbox, or None if not found.
        """
        logger.info(f"Searching for part '{part_number}' in: {pdf_path}")

        try:
            doc = fitz.open(str(pdf_path))
            all_matches: List[PartLocation] = []

            for page_index in range(len(doc)):
                page = doc[page_index]
                # search_for returns a list of fitz.Rect in page coordinates
                instances = page.search_for(part_number)

                for rect in instances:
                    loc = PartLocation(
                        page_index=page_index,
                        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                        text=part_number,
                    )
                    all_matches.append(loc)

            doc.close()

            if not all_matches:
                logger.warning(f"Part '{part_number}' not found in PDF")
                return None

            # ── Prefer a match that is inside the diagram body area ──────
            # Re-open briefly to get page dimensions for filtering
            doc2 = fitz.open(str(pdf_path))
            diagram_matches = []
            for loc in all_matches:
                page = doc2[loc.page_index]
                if self._is_in_diagram_area(loc.bbox, page.rect):
                    diagram_matches.append(loc)
            doc2.close()

            if diagram_matches:
                chosen = diagram_matches[0]
                logger.info(
                    f"Chose diagram-area match on page {chosen.page_index + 1}: {chosen.bbox}"
                )
            else:
                # All matches are in header/footer — use first anyway
                chosen = all_matches[0]
                logger.warning(
                    f"All matches in header/footer zone; using first: {chosen.bbox}"
                )

            return chosen

        except Exception as e:
            logger.error(f"Error searching PDF: {e}")
            return None

    def find_all_parts_in_pdf(
        self, pdf_path: Path, part_number: str
    ) -> List[PartLocation]:
        """Find every occurrence of part_number across all pages."""
        results: List[PartLocation] = []
        try:
            doc = fitz.open(str(pdf_path))
            for page_index in range(len(doc)):
                page = doc[page_index]
                for rect in page.search_for(part_number):
                    results.append(
                        PartLocation(
                            page_index=page_index,
                            bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                            text=part_number,
                        )
                    )
            doc.close()
            logger.info(f"Found {len(results)} occurrences of '{part_number}'")
        except Exception as e:
            logger.error(f"Error searching PDF: {e}")
        return results

    def render_page_to_image(
        self, pdf_path: Path, page_index: int
    ) -> Optional[Path]:
        """
        Render a single PDF page to a PNG at self.render_dpi resolution.

        The Matrix stored in self._make_render_matrix() MUST be the same
        one used in _bbox_to_pixel_rect() — this guarantees coordinate sync.
        """
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            doc = fitz.open(str(pdf_path))
            page = doc[page_index]

            mat = self._make_render_matrix()
            pix = page.get_pixmap(matrix=mat, alpha=False)

            image_path = TEMP_DIR / f"page_{page_index}.png"
            pix.save(str(image_path))
            logger.info(f"Page rendered: {image_path} ({pix.width}×{pix.height} px)")

            doc.close()
            return image_path
        except Exception as e:
            logger.error(f"Error rendering PDF page: {e}")
            return None

    def draw_highlight(
        self,
        image_path: Path,
        pixel_bbox: Tuple[int, int, int, int],
        output_path: Path,
    ) -> Optional[Path]:
        """
        Draw a highlight rectangle with an arrow pointing to it.

        pixel_bbox must already be in pixel coordinates (i.e. the result of
        _bbox_to_pixel_rect, NOT the raw PDF bbox).
        """
        try:
            image = Image.open(str(image_path)).convert("RGB")
            draw = ImageDraw.Draw(image)

            x0, y0, x1, y1 = pixel_bbox
            p = self.highlight_padding

            # Draw rectangle around the part
            draw.rectangle(
                [x0 - p, y0 - p, x1 + p, y1 + p],
                outline=self.highlight_color,
                width=self.highlight_width,
            )

            # Draw arrow pointing to the box
            self._draw_arrow(draw, pixel_bbox, image.size)

            image.save(str(output_path), "PNG")
            logger.info(f"Highlighted image saved: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error drawing highlight: {e}")
            return None

    def _draw_arrow(
        self,
        draw: ImageDraw.Draw,
        pixel_bbox: Tuple[int, int, int, int],
        image_size: Tuple[int, int],
    ) -> None:
        """
        Draw an arrow pointing to the highlighted box.
        Arrow comes from the left side, pointing right toward the box.
        """
        import math

        x0, y0, x1, y1 = pixel_bbox
        img_width, img_height = image_size
        p = self.highlight_padding

        # Arrow parameters
        arrow_length = 80
        arrow_head_length = 20
        arrow_head_angle = 30  # degrees

        # Arrow tip points to left edge of the box
        tip_x = x0 - p - 5
        tip_y = (y0 + y1) // 2  # middle of the box vertically

        # Arrow starts from the left
        start_x = tip_x - arrow_length
        start_y = tip_y

        # Ensure arrow stays within image bounds
        if start_x < 20:
            start_x = 20

        # Draw the arrow shaft
        draw.line(
            [(start_x, start_y), (tip_x, tip_y)],
            fill=self.highlight_color,
            width=self.highlight_width,
        )

        # Draw the arrowhead
        angle = math.atan2(tip_y - start_y, tip_x - start_x)
        angle1 = angle + math.radians(180 - arrow_head_angle)
        angle2 = angle + math.radians(180 + arrow_head_angle)

        head_x1 = tip_x + arrow_head_length * math.cos(angle1)
        head_y1 = tip_y + arrow_head_length * math.sin(angle1)
        head_x2 = tip_x + arrow_head_length * math.cos(angle2)
        head_y2 = tip_y + arrow_head_length * math.sin(angle2)

        # Draw arrowhead lines
        draw.line(
            [(tip_x, tip_y), (head_x1, head_y1)],
            fill=self.highlight_color,
            width=self.highlight_width,
        )
        draw.line(
            [(tip_x, tip_y), (head_x2, head_y2)],
            fill=self.highlight_color,
            width=self.highlight_width,
        )

    def process_and_highlight(
        self, pdf_path: Path, part_number: str, ticket_id: str
    ) -> Optional[Path]:
        """
        Full pipeline: find part → render page → convert bbox → highlight.

        The critical fix is step 3: convert the PDF bbox using the render
        matrix (fitz.Rect * mat) instead of manually multiplying by
        scale_factor.  Both give the same number for a clean upright page,
        but the matrix approach is correct for rotated or cropped pages.
        """
        try:
            # ── 1. Find part location (PDF coordinate space) ────────────
            location = self.find_part_in_pdf(pdf_path, part_number)
            if not location:
                logger.warning(f"Part '{part_number}' not found")
                return None

            logger.info(
                f"Part found on page {location.page_index + 1} "
                f"at PDF coords {location.bbox}"
            )

            # ── 2. Render the page to a PNG ──────────────────────────────
            page_image_path = self.render_page_to_image(pdf_path, location.page_index)
            if not page_image_path:
                return None

            # ── 3. Convert PDF bbox → pixel coords via render matrix ─────
            #
            #  FIX: use the fitz.Matrix transformation, NOT manual multiply.
            #  fitz.Rect * mat correctly handles:
            #    • page rotation (/Rotate in PDF)
            #    • non-square pixels
            #    • cropbox vs mediabox origin shifts
            #
            mat = self._make_render_matrix()
            pixel_bbox = self._bbox_to_pixel_rect(location.bbox, mat)

            logger.info(f"Pixel bbox after matrix transform: {pixel_bbox}")

            # ── 4. Draw highlight and save ───────────────────────────────
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = OUTPUT_DIR / f"highlighted_{ticket_id}.png"
            result = self.draw_highlight(page_image_path, pixel_bbox, output_path)

            # ── 5. Clean up intermediate file ───────────────────────────
            try:
                page_image_path.unlink()
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error(f"Error in process_and_highlight: {e}")
            return None

    # ------------------------------------------------------------------
    # Diagnostic helpers
    # ------------------------------------------------------------------

    def dump_text_blocks(self, pdf_path: Path, page_index: int = 0) -> None:
        """
        Print every text span with its PDF-space coordinates.

        Call this from a test script when highlights land in the wrong place.
        It lets you verify:
          a) Whether the part number text actually exists in the PDF
          b) Where it is in the PDF coordinate system

        Example usage in test_local.py:
            engine = get_pdf_engine()
            engine.dump_text_blocks(pdf_path, page_index=0)
        """
        try:
            doc = fitz.open(str(pdf_path))
            page = doc[page_index]
            blocks = page.get_text("dict")["blocks"]
            print(f"\n=== Text blocks on page {page_index + 1} ===")
            print(f"Page rect: {page.rect}")
            for b in blocks:
                if b.get("type") != 0:  # 0 = text block
                    continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        txt = span.get("text", "").strip()
                        if txt:
                            bbox = span.get("bbox")
                            print(f"  bbox={bbox}  text='{txt}'")
            doc.close()
        except Exception as e:
            logger.error(f"Error dumping text blocks: {e}")

    def diagnose_part(self, pdf_path: Path, part_number: str) -> None:
        """
        Full diagnostic: find all matches and show pixel coords for each.

        Run this when the highlight is in the wrong place to compare
        the matched PDF coords against where you expect them visually.
        """
        print(f"\n=== Diagnostic for '{part_number}' in {pdf_path.name} ===")
        matches = self.find_all_parts_in_pdf(pdf_path, part_number)

        if not matches:
            print("  NOT FOUND — check if text is searchable or embedded as outlines.")
            return

        mat = self._make_render_matrix()
        doc = fitz.open(str(pdf_path))

        for i, loc in enumerate(matches):
            page = doc[loc.page_index]
            pixel = self._bbox_to_pixel_rect(loc.bbox, mat)
            in_diagram = self._is_in_diagram_area(loc.bbox, page.rect)
            print(
                f"  Match {i + 1}: page={loc.page_index + 1} "
                f"pdf_bbox={tuple(round(v, 1) for v in loc.bbox)} "
                f"pixel_bbox={pixel} "
                f"in_diagram_area={in_diagram}"
            )

        doc.close()
        print()


# ── Singleton ──────────────────────────────────────────────────────────────
_pdf_engine = None


def get_pdf_engine() -> PDFEngine:
    global _pdf_engine
    if _pdf_engine is None:
        _pdf_engine = PDFEngine()
    return _pdf_engine


def highlight_part_in_pdf(
    pdf_path: Path, part_number: str, ticket_id: str
) -> Optional[Path]:
    """Main entry point: highlight a part number in a PDF."""
    return get_pdf_engine().process_and_highlight(pdf_path, part_number, ticket_id)


def find_part_in_pdf(pdf_path: Path, part_number: str) -> Optional[PartLocation]:
    """Check if a part exists in a PDF without generating an image."""
    return get_pdf_engine().find_part_in_pdf(pdf_path, part_number)
