"""
Local Test Script - View highlighted diagrams without Freshdesk

Usage:
    python test_local.py <model_number> <part_number>
    
Examples:
    python test_local.py 230.1000 230.1000-1214
    python test_local.py 240.1170 240.1170-1234
"""
import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from drive_service import download_pdf_from_drive, get_drive_service
from pdf_engine import highlight_part_in_pdf, get_pdf_engine
from config import TEMP_DIR

def list_available_models():
    """Show available models from Drive."""
    print("\nAvailable models in Drive:")
    print("-" * 40)
    service = get_drive_service()
    pdfs = service.list_pdfs_in_folder()
    for pdf in pdfs:
        print(f"  - {pdf['name']}")
    print()

def list_parts_in_pdf(pdf_path: Path, limit: int = 20):
    """Show part numbers found in a PDF."""
    import fitz
    import re
    
    doc = fitz.open(str(pdf_path))
    parts = set()
    
    # Pattern for part numbers
    part_pattern = r'\d{3}\.\d{4}-\d{4,5}'
    
    for page in doc:
        text = page.get_text()
        found = re.findall(part_pattern, text)
        parts.update(found)
    
    doc.close()
    
    print(f"\nPart numbers found in PDF (showing first {limit}):")
    print("-" * 40)
    for i, part in enumerate(sorted(parts)[:limit]):
        print(f"  {part}")
    print()
    
    return list(parts)

def test_highlight(model_number: str, part_number: str):
    """Download PDF, highlight part, save locally."""
    
    print(f"\n{'='*60}")
    print(f"Testing Highlight")
    print(f"{'='*60}")
    print(f"Model: {model_number}")
    print(f"Part:  {part_number}")
    print()
    
    # Step 1: Download PDF
    print("[1/3] Downloading PDF from Google Drive...")
    pdf_path = download_pdf_from_drive(model_number)
    
    if not pdf_path:
        print(f"ERROR: Could not find/download PDF for model: {model_number}")
        list_available_models()
        return None
    
    print(f"      Downloaded: {pdf_path}")
    print(f"      Size: {pdf_path.stat().st_size:,} bytes")
    
    # Step 2: Find and highlight part
    print(f"\n[2/3] Searching for part '{part_number}' in PDF...")
    
    # First check if part exists
    engine = get_pdf_engine()
    location = engine.find_part_in_pdf(pdf_path, part_number)
    
    if not location:
        print(f"      Part '{part_number}' NOT FOUND in PDF")
        print("\n      Available parts in this PDF:")
        parts = list_parts_in_pdf(pdf_path)
        return None
    
    print(f"      Found on page {location.page_index + 1}")
    print(f"      Location: {location.bbox}")
    
    # Step 3: Generate highlighted image
    print(f"\n[3/3] Generating highlighted image...")
    
    output_name = f"{model_number}_{part_number.replace('.', '_').replace('-', '_')}"
    output_path = highlight_part_in_pdf(pdf_path, part_number, output_name)
    
    if not output_path:
        print("ERROR: Failed to generate highlighted image")
        return None
    
    print(f"      Saved: {output_path}")
    print(f"      Size: {output_path.stat().st_size:,} bytes")
    
    # Open the image
    print(f"\n{'='*60}")
    print(f"SUCCESS! Opening image...")
    print(f"{'='*60}")
    
    # Try to open with default viewer
    try:
        os.startfile(str(output_path))
        print(f"\nImage opened in default viewer.")
    except Exception as e:
        print(f"\nCould not auto-open. View manually at:")
        print(f"  {output_path}")
    
    return output_path

def interactive_mode():
    """Interactive mode for testing multiple parts."""
    print("\n" + "="*60)
    print("Part Diagram Highlighter - Interactive Mode")
    print("="*60)
    
    # List available models
    list_available_models()
    
    while True:
        print("\nEnter model and part number (or 'q' to quit):")
        
        model = input("Model number (e.g., 230.1000): ").strip()
        if model.lower() == 'q':
            break
        
        if not model:
            continue
        
        # Download and show parts
        print(f"\nDownloading {model}...")
        pdf_path = download_pdf_from_drive(model)
        
        if not pdf_path:
            print(f"Model not found!")
            continue
        
        # Show available parts
        parts = list_parts_in_pdf(pdf_path)
        
        part = input("Part number to highlight (or 'skip'): ").strip()
        if part.lower() == 'skip' or not part:
            continue
        
        # Highlight
        test_highlight(model, part)
        
        print("\n" + "-"*40)

if __name__ == "__main__":
    # Ensure temp directory exists
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    if len(sys.argv) >= 3:
        # Command line mode
        model = sys.argv[1]
        part = sys.argv[2]
        test_highlight(model, part)
    elif len(sys.argv) == 2 and sys.argv[1] == '-i':
        # Interactive mode
        interactive_mode()
    else:
        # Default: test with known working example
        print("Usage:")
        print("  python test_local.py <model> <part>")
        print("  python test_local.py -i              (interactive mode)")
        print()
        print("Running demo with 230.1000 and part 230.1000-1214...")
        test_highlight("230.1000", "230.1000-1214")
