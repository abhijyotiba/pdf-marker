"""
Test Freshdesk integration with a specific ticket.

Usage:
  python test_freshdesk.py <ticket_id>                    # Auto-extract model/part from ticket
  python test_freshdesk.py <ticket_id> <model> <part>     # Manual model/part

Example:
  python test_freshdesk.py 12345
  python test_freshdesk.py 12345 230.1000 230.1000-2352
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from freshdesk_service import get_freshdesk_service, add_highlighted_diagram
from drive_service import DriveService
from pdf_engine import PDFEngine
from config import OUTPUT_DIR
import re


def test_freshdesk_connection():
    """Test that we can connect to Freshdesk."""
    print("=" * 60)
    print("Testing Freshdesk Connection")
    print("=" * 60)
    
    service = get_freshdesk_service()
    print(f"Domain: {service.domain}")
    print(f"API URL: {service.base_url}")
    print()


def get_ticket_info(ticket_id: int):
    """Fetch and display ticket information."""
    service = get_freshdesk_service()
    
    print(f"Fetching ticket #{ticket_id}...")
    ticket = service.get_ticket(ticket_id)
    
    if not ticket:
        print("ERROR: Could not fetch ticket. Check your API key and domain.")
        return None
    
    print(f"  Subject: {ticket.get('subject', 'N/A')}")
    print(f"  Status: {ticket.get('status', 'N/A')}")
    print(f"  Priority: {ticket.get('priority', 'N/A')}")
    
    description = ticket.get('description_text') or ticket.get('description') or ''
    print(f"  Description preview: {description[:100]}..." if len(description) > 100 else f"  Description: {description}")
    
    return ticket


def extract_model_part(text: str):
    """Extract model and part numbers from text."""
    model_pattern = r'\d{3}\.\d{4}[A-Z]?|K\.\d{4}'
    part_pattern = r'\d{3}\.\d{4}-\d{4,5}'
    
    model_match = re.search(model_pattern, text)
    part_match = re.search(part_pattern, text)
    
    return (
        model_match.group() if model_match else None,
        part_match.group() if part_match else None
    )


def process_ticket(ticket_id: int, model: str = None, part: str = None):
    """
    Process a ticket: download PDF, highlight part, add private note.
    """
    print("=" * 60)
    print(f"Processing Ticket #{ticket_id}")
    print("=" * 60)
    
    # Step 1: Get ticket info
    ticket = get_ticket_info(ticket_id)
    if not ticket:
        return False
    
    # Step 2: Extract or use provided model/part
    if not model or not part:
        full_text = f"{ticket.get('subject', '')} {ticket.get('description_text', '')}"
        extracted_model, extracted_part = extract_model_part(full_text)
        model = model or extracted_model
        part = part or extracted_part
    
    print()
    print(f"Model: {model}")
    print(f"Part:  {part}")
    
    if not model:
        print("ERROR: No model number found in ticket")
        return False
    
    if not part:
        print("ERROR: No part number found in ticket")
        return False
    
    # Step 3: Download PDF
    print()
    print("[1/4] Downloading PDF from Google Drive...")
    ds = DriveService()
    pdf_path = ds.download_pdf_by_model(model)
    
    if not pdf_path:
        print(f"ERROR: PDF not found for model {model}")
        return False
    
    print(f"      Downloaded: {pdf_path}")
    
    # Step 4: Find and highlight part
    print()
    print(f"[2/4] Searching for part '{part}' in PDF...")
    engine = PDFEngine()
    
    # Generate unique filename for this ticket
    safe_part = part.replace(".", "_").replace("-", "_")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"highlighted_ticket_{ticket_id}_{safe_part}.png"
    
    result = engine.process_and_highlight(pdf_path, part, f"ticket_{ticket_id}_{safe_part}")
    
    if not result:
        print(f"ERROR: Part '{part}' not found in PDF")
        return False
    
    print(f"      Highlighted image: {result}")
    
    # Step 5: Add private note to ticket
    print()
    print("[3/4] Adding private note with image to ticket...")
    
    success = add_highlighted_diagram(ticket_id, result, part)
    
    if success:
        print("      SUCCESS! Private note added to ticket.")
    else:
        print("      ERROR: Failed to add note to ticket")
        return False
    
    # Step 6: Show summary
    print()
    print("[4/4] Done!")
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Ticket: #{ticket_id}")
    print(f"Model:  {model}")
    print(f"Part:   {part}")
    print(f"Image:  {result}")
    print(f"Status: Private note added successfully!")
    print()
    print("Check the ticket in Freshdesk to see the private note.")
    
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nAvailable PDFs:")
        ds = DriveService()
        files = ds.list_pdfs()
        for f in files[:5]:
            print(f"  - {f['name']}")
        sys.exit(1)
    
    ticket_id = int(sys.argv[1])
    
    # Optional: manual model/part override
    model = sys.argv[2] if len(sys.argv) > 2 else None
    part = sys.argv[3] if len(sys.argv) > 3 else None
    
    # Test connection first
    test_freshdesk_connection()
    
    # Process the ticket
    success = process_ticket(ticket_id, model, part)
    
    sys.exit(0 if success else 1)
