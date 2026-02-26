"""
Freshdesk Service - Handles Freshdesk API integration
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from requests.auth import HTTPBasicAuth

from config import FRESHDESK_CONFIG

logger = logging.getLogger(__name__)


class FreshdeskService:
    """Handles Freshdesk API operations."""
    
    def __init__(self):
        """Initialize the Freshdesk service with configuration."""
        self.domain = FRESHDESK_CONFIG["DOMAIN"]
        self.api_key = FRESHDESK_CONFIG["API_KEY"]
        self.base_url = f"https://{self.domain}.freshdesk.com/api/v2"
        self.auth = HTTPBasicAuth(self.api_key, "X")
        
        # Default headers
        self.headers = {
            "Content-Type": "application/json"
        }
    
    def get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch ticket details from Freshdesk.
        
        Args:
            ticket_id: The Freshdesk ticket ID
            
        Returns:
            Ticket data dictionary, or None if failed
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}"
            
            logger.info(f"Fetching ticket: {ticket_id}")
            
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            ticket_data = response.json()
            
            logger.info(f"Ticket fetched successfully: {ticket_id}")
            return ticket_data
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching ticket {ticket_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching ticket {ticket_id}: {e}")
            return None
    
    def get_ticket_conversations(self, ticket_id: int) -> Optional[list]:
        """
        Fetch conversations (notes and replies) for a ticket.
        
        Args:
            ticket_id: The Freshdesk ticket ID
            
        Returns:
            List of conversations, or None if failed
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}/conversations"
            
            logger.info(f"Fetching conversations for ticket: {ticket_id}")
            
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            conversations = response.json()
            
            logger.info(f"Found {len(conversations)} conversations")
            return conversations
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching conversations: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching conversations: {e}")
            return None
    
    def add_private_note(self, ticket_id: int, body: str, 
                         attachment_path: Optional[Path] = None) -> bool:
        """
        Add a private note to a ticket, optionally with an attachment.
        
        Args:
            ticket_id: The Freshdesk ticket ID
            body: The note body text (can include HTML)
            attachment_path: Optional path to a file to attach
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}/notes"
            
            logger.info(f"Adding private note to ticket: {ticket_id}")
            
            if attachment_path and attachment_path.exists():
                # Use multipart form data for attachments
                files = {
                    'attachments[]': (
                        attachment_path.name,
                        open(str(attachment_path), 'rb'),
                        'image/png'
                    )
                }
                data = {
                    'body': body,
                    'private': 'true'
                }
                
                response = requests.post(
                    url,
                    auth=self.auth,
                    files=files,
                    data=data,
                    timeout=60
                )
            else:
                # JSON request without attachment
                json_data = {
                    'body': body,
                    'private': True
                }
                
                response = requests.post(
                    url,
                    auth=self.auth,
                    headers=self.headers,
                    json=json_data,
                    timeout=30
                )
            
            response.raise_for_status()
            logger.info(f"Private note added successfully to ticket {ticket_id}")
            return True
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error adding note to ticket {ticket_id}: {e}")
            logger.error(f"Response: {e.response.text if e.response else 'No response'}")
            return False
        except Exception as e:
            logger.error(f"Error adding note to ticket {ticket_id}: {e}")
            return False
    
    def add_reply(self, ticket_id: int, body: str,
                  attachment_path: Optional[Path] = None) -> bool:
        """
        Add a public reply to a ticket, optionally with an attachment.
        
        Args:
            ticket_id: The Freshdesk ticket ID
            body: The reply body text (can include HTML)
            attachment_path: Optional path to a file to attach
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}/reply"
            
            logger.info(f"Adding reply to ticket: {ticket_id}")
            
            if attachment_path and attachment_path.exists():
                # Use multipart form data for attachments
                files = {
                    'attachments[]': (
                        attachment_path.name,
                        open(str(attachment_path), 'rb'),
                        'image/png'
                    )
                }
                data = {
                    'body': body
                }
                
                response = requests.post(
                    url,
                    auth=self.auth,
                    files=files,
                    data=data,
                    timeout=60
                )
            else:
                # JSON request without attachment
                json_data = {
                    'body': body
                }
                
                response = requests.post(
                    url,
                    auth=self.auth,
                    headers=self.headers,
                    json=json_data,
                    timeout=30
                )
            
            response.raise_for_status()
            logger.info(f"Reply added successfully to ticket {ticket_id}")
            return True
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error adding reply to ticket {ticket_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error adding reply to ticket {ticket_id}: {e}")
            return False
    
    def add_tag(self, ticket_id: int, tags: list) -> bool:
        """
        Add tags to a ticket.
        
        Args:
            ticket_id: The Freshdesk ticket ID
            tags: List of tag strings to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/tickets/{ticket_id}"
            
            # First get current tags
            current_ticket = self.get_ticket(ticket_id)
            if not current_ticket:
                return False
            
            current_tags = current_ticket.get('tags', [])
            all_tags = list(set(current_tags + tags))
            
            json_data = {
                'tags': all_tags
            }
            
            response = requests.put(
                url,
                auth=self.auth,
                headers=self.headers,
                json=json_data,
                timeout=30
            )
            
            response.raise_for_status()
            logger.info(f"Tags added to ticket {ticket_id}: {tags}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding tags to ticket {ticket_id}: {e}")
            return False


# Singleton instance
_freshdesk_service = None


def get_freshdesk_service() -> FreshdeskService:
    """Get or create the Freshdesk service singleton."""
    global _freshdesk_service
    if _freshdesk_service is None:
        _freshdesk_service = FreshdeskService()
    return _freshdesk_service


def add_highlighted_diagram(ticket_id: int, image_path: Path, 
                            part_number: str) -> bool:
    """
    Add a highlighted diagram image to a Freshdesk ticket as a private note.
    
    This is the main entry point for uploading diagram images.
    
    Args:
        ticket_id: The Freshdesk ticket ID
        image_path: Path to the highlighted diagram image
        part_number: The part number that was highlighted
        
    Returns:
        True if successful, False otherwise
    """
    service = get_freshdesk_service()
    
    body = f"""
    <p><strong>Part Diagram - Highlighted</strong></p>
    <p>Part Number: <code>{part_number}</code></p>
    <p>Please see the highlighted part in the attached diagram image.</p>
    """
    
    return service.add_private_note(ticket_id, body, image_path)


def add_error_note(ticket_id: int, error_type: str, details: str = "") -> bool:
    """
    Add an error message as a private note.
    
    Args:
        ticket_id: The Freshdesk ticket ID
        error_type: Type of error (e.g., "pdf_not_found", "part_not_found")
        details: Additional error details
        
    Returns:
        True if successful, False otherwise
    """
    service = get_freshdesk_service()
    
    error_messages = {
        "pdf_not_found": "Diagram PDF not found for the specified model number.",
        "part_not_found": "Part number not found in the diagram.",
        "processing_error": "An error occurred while processing the diagram.",
        "extraction_error": "Could not extract model/part number from the ticket.",
    }
    
    message = error_messages.get(error_type, f"Error: {error_type}")
    
    body = f"""
    <p><strong>Part Diagram System - Error</strong></p>
    <p>{message}</p>
    {f'<p>Details: {details}</p>' if details else ''}
    """
    
    return service.add_private_note(ticket_id, body)
