"""
Part Diagram POC - Main Application

This Flask application receives Freshdesk webhooks, processes part diagram
requests, and responds with highlighted diagram images.
"""
import re
import logging
from pathlib import Path
from typing import Optional, Tuple

from flask import Flask, request, jsonify

from config import (
    REGEX_PATTERNS, 
    SERVER_CONFIG, 
    LOGGING_CONFIG, 
    TEMP_DIR,
    BASE_DIR
)
from drive_service import download_pdf_from_drive
from pdf_engine import highlight_part_in_pdf
from freshdesk_service import (
    add_highlighted_diagram, 
    add_error_note,
    get_freshdesk_service
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOGGING_CONFIG["LOG_LEVEL"]),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGGING_CONFIG["LOG_FILE"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)


def extract_model_and_part(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract model number and part number from text.
    
    Args:
        text: The text to search (ticket description, subject, etc.)
        
    Returns:
        Tuple of (model_number, part_number), either can be None
    """
    model_number = None
    part_number = None
    
    if not text:
        return None, None
    
    # Extract model number (XXX.XXXX)
    model_match = re.search(REGEX_PATTERNS["MODEL"], text)
    if model_match:
        model_number = model_match.group()
        logger.info(f"Extracted model number: {model_number}")
    
    # Extract part number (XXX.XXXX-XXXXX)
    part_match = re.search(REGEX_PATTERNS["PART"], text)
    if part_match:
        part_number = part_match.group()
        logger.info(f"Extracted part number: {part_number}")
    
    return model_number, part_number


def cleanup_temp_files(ticket_id: str):
    """
    Clean up temporary files created during processing.
    
    Args:
        ticket_id: The ticket ID used in file names
    """
    try:
        for file_path in TEMP_DIR.glob(f"*{ticket_id}*"):
            file_path.unlink()
            logger.debug(f"Cleaned up: {file_path}")
        
        # Also clean up any PDF files older than 1 hour
        import time
        current_time = time.time()
        for file_path in TEMP_DIR.glob("*.pdf"):
            if current_time - file_path.stat().st_mtime > 3600:
                file_path.unlink()
                logger.debug(f"Cleaned up old PDF: {file_path}")
                
    except Exception as e:
        logger.warning(f"Error cleaning up temp files: {e}")


def process_diagram_request(ticket_id: int, description: str, 
                            subject: str = "") -> dict:
    """
    Process a diagram highlighting request.
    
    Args:
        ticket_id: The Freshdesk ticket ID
        description: The ticket description
        subject: The ticket subject
        
    Returns:
        Result dictionary with status and message
    """
    try:
        # Combine subject and description for extraction
        full_text = f"{subject} {description}"
        
        # Step 1: Extract model and part numbers
        model_number, part_number = extract_model_and_part(full_text)
        
        if not model_number:
            logger.warning(f"Ticket {ticket_id}: No model number found")
            add_error_note(ticket_id, "extraction_error", 
                          "Model number not found in ticket")
            return {
                "status": "error",
                "message": "Model number not found in ticket"
            }
        
        if not part_number:
            logger.warning(f"Ticket {ticket_id}: No part number found")
            add_error_note(ticket_id, "extraction_error", 
                          "Part number not found in ticket")
            return {
                "status": "error",
                "message": "Part number not found in ticket"
            }
        
        logger.info(f"Processing ticket {ticket_id}: Model={model_number}, Part={part_number}")
        
        # Step 2: Download PDF from Google Drive
        pdf_path = download_pdf_from_drive(model_number)
        
        if not pdf_path:
            logger.warning(f"Ticket {ticket_id}: PDF not found for model {model_number}")
            add_error_note(ticket_id, "pdf_not_found", 
                          f"Model: {model_number}")
            return {
                "status": "error",
                "message": f"PDF not found for model: {model_number}"
            }
        
        # Step 3: Find and highlight the part
        highlighted_image_path = highlight_part_in_pdf(
            pdf_path, 
            part_number, 
            str(ticket_id)
        )
        
        if not highlighted_image_path:
            logger.warning(f"Ticket {ticket_id}: Part {part_number} not found in PDF")
            add_error_note(ticket_id, "part_not_found", 
                          f"Part: {part_number}, Model: {model_number}")
            # Clean up PDF
            try:
                pdf_path.unlink()
            except Exception:
                pass
            return {
                "status": "error",
                "message": f"Part {part_number} not found in diagram"
            }
        
        # Step 4: Upload to Freshdesk
        success = add_highlighted_diagram(ticket_id, highlighted_image_path, part_number)
        
        # Step 5: Cleanup
        try:
            pdf_path.unlink()
            highlighted_image_path.unlink()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
        
        if success:
            logger.info(f"Ticket {ticket_id}: Diagram attached successfully")
            return {
                "status": "success",
                "message": "Highlighted diagram attached to ticket",
                "model": model_number,
                "part": part_number
            }
        else:
            return {
                "status": "error",
                "message": "Failed to attach diagram to ticket"
            }
            
    except Exception as e:
        logger.exception(f"Error processing ticket {ticket_id}: {e}")
        add_error_note(ticket_id, "processing_error", str(e))
        return {
            "status": "error",
            "message": f"Processing error: {str(e)}"
        }


@app.route("/", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "Part Diagram POC"
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Freshdesk webhook endpoint.
    
    Receives ticket data and processes diagram requests.
    """
    try:
        logger.info("Received webhook request")
        
        # Parse the webhook payload
        data = request.get_json() or request.form.to_dict()
        
        if not data:
            logger.warning("Empty webhook payload")
            return jsonify({"error": "Empty payload"}), 400
        
        logger.debug(f"Webhook payload: {data}")
        
        # Extract ticket information
        # Freshdesk webhook format can vary, handle multiple formats
        ticket_id = (
            data.get("ticket_id") or 
            data.get("freshdesk_webhook", {}).get("ticket_id") or
            data.get("id")
        )
        
        if not ticket_id:
            logger.warning("No ticket ID in webhook")
            return jsonify({"error": "No ticket ID"}), 400
        
        ticket_id = int(ticket_id)
        
        # Get description and subject
        description = (
            data.get("ticket_description") or
            data.get("description") or
            data.get("freshdesk_webhook", {}).get("ticket_description") or
            ""
        )
        
        subject = (
            data.get("ticket_subject") or
            data.get("subject") or
            data.get("freshdesk_webhook", {}).get("ticket_subject") or
            ""
        )
        
        # Check for trigger tag if using tag-based triggering
        tags = data.get("tags") or data.get("ticket_tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        
        # Optional: Only process if generate-diagram tag is present
        # Uncomment the following lines to enable tag-based triggering
        # if "generate-diagram" not in tags:
        #     logger.info(f"Ticket {ticket_id}: generate-diagram tag not present, skipping")
        #     return jsonify({"status": "skipped", "reason": "No trigger tag"}), 200
        
        # If description is empty, fetch from Freshdesk API
        if not description:
            try:
                service = get_freshdesk_service()
                ticket = service.get_ticket(ticket_id)
                if ticket:
                    description = ticket.get("description_text") or ticket.get("description") or ""
                    subject = subject or ticket.get("subject") or ""
            except Exception as e:
                logger.warning(f"Could not fetch ticket details: {e}")
        
        # Process the diagram request
        result = process_diagram_request(ticket_id, description, subject)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/test", methods=["POST"])
def test_endpoint():
    """
    Test endpoint for manual testing without Freshdesk.
    
    Expects JSON with: ticket_id, model, part
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
        
        ticket_id = data.get("ticket_id", 99999)
        model = data.get("model")
        part = data.get("part")
        
        if not model or not part:
            return jsonify({
                "error": "Both 'model' and 'part' are required"
            }), 400
        
        # Create synthetic description
        description = f"Model: {model}, Part: {part}"
        
        result = process_diagram_request(ticket_id, description, "")
        return jsonify(result), 200
        
    except Exception as e:
        logger.exception(f"Test endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/list-pdfs", methods=["GET"])
def list_pdfs():
    """
    Debug endpoint to list available PDFs in Google Drive.
    """
    try:
        from drive_service import get_drive_service
        
        service = get_drive_service()
        pdfs = service.list_pdfs_in_folder()
        
        return jsonify({
            "count": len(pdfs),
            "files": pdfs
        }), 200
        
    except Exception as e:
        logger.exception(f"Error listing PDFs: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Ensure temp directory exists
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting Part Diagram POC server...")
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info(f"Temp directory: {TEMP_DIR}")
    
    app.run(
        host=SERVER_CONFIG["HOST"],
        port=SERVER_CONFIG["PORT"],
        debug=SERVER_CONFIG["DEBUG"]
    )
