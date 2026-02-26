"""
PDF Highlight Engine - Handles PDF processing and highlighting
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
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    text: str


class PDFEngine:
    """Handles PDF processing, part location, and highlighting."""
    
    def __init__(self):
        """Initialize the PDF engine with configuration."""
        self.render_dpi = PDF_CONFIG["RENDER_DPI"]
        self.base_dpi = PDF_CONFIG["PDF_BASE_DPI"]
        self.scale_factor = self.render_dpi / self.base_dpi
        
        self.highlight_color = PDF_CONFIG["HIGHLIGHT_COLOR"]
        self.highlight_width = PDF_CONFIG["HIGHLIGHT_WIDTH"]
        self.highlight_padding = PDF_CONFIG["HIGHLIGHT_PADDING"]
    
    def find_part_in_pdf(self, pdf_path: Path, part_number: str) -> Optional[PartLocation]:
        """
        Search for a part number in a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            part_number: The part number to search for
            
        Returns:
            PartLocation if found, None otherwise
        """
        try:
            logger.info(f"Searching for part '{part_number}' in PDF: {pdf_path}")
            
            doc = fitz.open(str(pdf_path))
            
            for page_index in range(len(doc)):
                page = doc[page_index]
                instances = page.search_for(part_number)
                
                if instances:
                    # Found the part number
                    bbox = instances[0]  # Take the first occurrence
                    logger.info(f"Found part on page {page_index + 1}, bbox: {bbox}")
                    doc.close()
                    return PartLocation(
                        page_index=page_index,
                        bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                        text=part_number
                    )
            
            doc.close()
            logger.warning(f"Part '{part_number}' not found in PDF")
            return None
            
        except Exception as e:
            logger.error(f"Error searching PDF: {e}")
            return None
    
    def find_all_parts_in_pdf(self, pdf_path: Path, part_number: str) -> List[PartLocation]:
        """
        Find all occurrences of a part number in a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            part_number: The part number to search for
            
        Returns:
            List of PartLocations for all occurrences
        """
        results = []
        
        try:
            doc = fitz.open(str(pdf_path))
            
            for page_index in range(len(doc)):
                page = doc[page_index]
                instances = page.search_for(part_number)
                
                for bbox in instances:
                    results.append(PartLocation(
                        page_index=page_index,
                        bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                        text=part_number
                    ))
            
            doc.close()
            logger.info(f"Found {len(results)} occurrences of '{part_number}'")
            return results
            
        except Exception as e:
            logger.error(f"Error searching PDF: {e}")
            return results
    
    def render_page_to_image(self, pdf_path: Path, page_index: int) -> Optional[Path]:
        """
        Render a specific PDF page to an image file.
        
        Args:
            pdf_path: Path to the PDF file
            page_index: Zero-based page index
            
        Returns:
            Path to the rendered image, or None if failed
        """
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            
            doc = fitz.open(str(pdf_path))
            page = doc[page_index]
            
            # Use transformation matrix for precise scaling
            # This ensures coordinates scale exactly as expected
            zoom = self.scale_factor
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Save as PNG
            image_path = TEMP_DIR / f"page_{page_index}.png"
            pix.save(str(image_path))
            
            logger.info(f"Page rendered to: {image_path} ({pix.width}x{pix.height})")
            doc.close()
            return image_path
            
        except Exception as e:
            logger.error(f"Error rendering PDF page: {e}")
            return None
    
    def scale_bbox(self, bbox: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
        """
        Scale PDF coordinates to image coordinates.
        
        Args:
            bbox: Original PDF coordinates (x0, y0, x1, y1)
            
        Returns:
            Scaled image coordinates
        """
        x0, y0, x1, y1 = bbox
        return (
            int(x0 * self.scale_factor),
            int(y0 * self.scale_factor),
            int(x1 * self.scale_factor),
            int(y1 * self.scale_factor)
        )
    
    def draw_highlight(self, image_path: Path, bbox: Tuple[int, int, int, int], 
                       output_path: Path) -> Optional[Path]:
        """
        Draw a highlight rectangle on an image.
        
        Args:
            image_path: Path to the image file
            bbox: Coordinates to highlight (x0, y0, x1, y1)
            output_path: Path to save the highlighted image
            
        Returns:
            Path to the highlighted image, or None if failed
        """
        try:
            image = Image.open(str(image_path))
            draw = ImageDraw.Draw(image)
            
            x0, y0, x1, y1 = bbox
            padding = self.highlight_padding
            
            # Draw the highlight rectangle
            draw.rectangle(
                [x0 - padding, y0 - padding, x1 + padding, y1 + padding],
                outline=self.highlight_color,
                width=self.highlight_width
            )
            
            # Save highlighted image
            image.save(str(output_path), "PNG")
            logger.info(f"Highlighted image saved to: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error drawing highlight: {e}")
            return None
    
    def process_and_highlight(self, pdf_path: Path, part_number: str, 
                              ticket_id: str) -> Optional[Path]:
        """
        Complete pipeline: find part, render page, highlight, save.
        
        This is the main entry point for the PDF engine.
        
        Args:
            pdf_path: Path to the PDF file
            part_number: Part number to find and highlight
            ticket_id: Ticket ID for naming the output file
            
        Returns:
            Path to the final highlighted image, or None if failed
        """
        try:
            # Step 1: Find the part in the PDF
            location = self.find_part_in_pdf(pdf_path, part_number)
            
            if not location:
                logger.warning(f"Part '{part_number}' not found in PDF")
                return None
            
            # Step 2: Render the page to image
            page_image_path = self.render_page_to_image(pdf_path, location.page_index)
            
            if not page_image_path:
                return None
            
            # Step 3: Scale the coordinates
            scaled_bbox = self.scale_bbox(location.bbox)
            
            # Step 4: Draw highlight and save to output directory
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = OUTPUT_DIR / f"highlighted_{ticket_id}.png"
            result = self.draw_highlight(page_image_path, scaled_bbox, output_path)
            
            # Clean up intermediate page image
            try:
                page_image_path.unlink()
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"Error in process_and_highlight: {e}")
            return None


# Singleton instance
_pdf_engine = None


def get_pdf_engine() -> PDFEngine:
    """Get or create the PDF engine singleton."""
    global _pdf_engine
    if _pdf_engine is None:
        _pdf_engine = PDFEngine()
    return _pdf_engine


def highlight_part_in_pdf(pdf_path: Path, part_number: str, ticket_id: str) -> Optional[Path]:
    """
    Main entry point: highlight a part number in a PDF.
    
    Args:
        pdf_path: Path to the PDF file
        part_number: Part number to find and highlight
        ticket_id: Ticket ID for naming the output
        
    Returns:
        Path to the highlighted image, or None if not found/failed
    """
    engine = get_pdf_engine()
    return engine.process_and_highlight(pdf_path, part_number, ticket_id)


def find_part_in_pdf(pdf_path: Path, part_number: str) -> Optional[PartLocation]:
    """
    Check if a part exists in a PDF without generating an image.
    
    Args:
        pdf_path: Path to the PDF file
        part_number: Part number to search for
        
    Returns:
        PartLocation if found, None otherwise
    """
    engine = get_pdf_engine()
    return engine.find_part_in_pdf(pdf_path, part_number)
