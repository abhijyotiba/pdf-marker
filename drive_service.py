"""
Google Drive Service - Handles PDF downloads from publicly shared Google Drive folder

Supports two methods:
1. Google Drive API with API key (for public folders - recommended)
2. Direct download with manual file ID mapping (fallback)

No service account required - just an API key or manual mapping.
"""
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import requests

from config import GOOGLE_DRIVE_CONFIG, TEMP_DIR

logger = logging.getLogger(__name__)


class DriveService:
    """Handles Google Drive operations for publicly shared PDF files."""
    
    # Google Drive API endpoint (works with API key for public files)
    API_LIST_URL = "https://www.googleapis.com/drive/v3/files"
    
    # Direct download URLs
    DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"
    CONFIRM_URL = "https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
    
    def __init__(self):
        """Initialize the Drive service for public folder access."""
        self.folder_id = GOOGLE_DRIVE_CONFIG["FOLDER_ID"]
        self.api_key = GOOGLE_DRIVE_CONFIG.get("API_KEY")
        self.file_mapping = GOOGLE_DRIVE_CONFIG.get("FILE_MAPPING", {})
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        self._file_cache: Dict[str, Tuple[str, str]] = {}
        
        # Pre-populate cache from file mapping
        for model, file_id in self.file_mapping.items():
            self._file_cache[model] = (file_id, f"{model}.pdf")
        
        logger.info(f"Google Drive service initialized (Folder: {self.folder_id})")
        if self.api_key:
            logger.info("Using API key for folder listing")
        if self.file_mapping:
            logger.info(f"Loaded {len(self.file_mapping)} files from manual mapping")
    
    def list_pdfs_in_folder(self) -> List[Dict[str, str]]:
        """
        List all PDF files in the shared Drive folder using API key.
        
        Returns:
            List of dictionaries with file info (id, name)
        """
        files = []
        
        # Method 1: Use API with API key (if available)
        if self.api_key:
            try:
                params = {
                    'q': f"'{self.folder_id}' in parents and mimeType='application/pdf' and trashed=false",
                    'key': self.api_key,
                    'fields': 'files(id,name,size)',
                    'pageSize': 100
                }
                
                response = self.session.get(self.API_LIST_URL, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                files = data.get('files', [])
                
                # Cache the results
                for f in files:
                    model_match = re.search(r'\d{3}\.\d{4}', f['name'])
                    if model_match:
                        self._file_cache[model_match.group()] = (f['id'], f['name'])
                
                logger.info(f"Found {len(files)} PDFs via API")
                return files
                
            except Exception as e:
                logger.error(f"API listing failed: {e}")
        
        # Method 2: Return files from manual mapping
        if self.file_mapping:
            for model, file_id in self.file_mapping.items():
                files.append({
                    'id': file_id,
                    'name': f"{model}.pdf"
                })
            logger.info(f"Returning {len(files)} PDFs from manual mapping")
            return files
        
        logger.warning("No API key and no file mapping configured")
        return []
    
    def search_pdf_by_model(self, model_number: str) -> Optional[Tuple[str, str]]:
        """
        Search for a PDF file by model number.
        
        Args:
            model_number: The model number to search for (e.g., "270.2000")
            
        Returns:
            Tuple of (file_id, file_name) if found, None otherwise
        """
        logger.info(f"Searching for model: {model_number}")
        
        # Check cache first
        if model_number in self._file_cache:
            logger.info(f"Found model {model_number} in cache")
            return self._file_cache[model_number]
        
        # Check manual mapping
        if model_number in self.file_mapping:
            file_id = self.file_mapping[model_number]
            result = (file_id, f"{model_number}.pdf")
            self._file_cache[model_number] = result
            logger.info(f"Found model {model_number} in file mapping")
            return result
        
        # Try API listing if available
        if self.api_key:
            try:
                params = {
                    'q': f"'{self.folder_id}' in parents and name contains '{model_number}' and mimeType='application/pdf'",
                    'key': self.api_key,
                    'fields': 'files(id,name)',
                    'pageSize': 1
                }
                
                response = self.session.get(self.API_LIST_URL, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                files = data.get('files', [])
                
                if files:
                    f = files[0]
                    result = (f['id'], f['name'])
                    self._file_cache[model_number] = result
                    logger.info(f"Found PDF for model {model_number}: {f['name']}")
                    return result
                    
            except Exception as e:
                logger.error(f"API search failed: {e}")
        
        # List all and search
        pdfs = self.list_pdfs_in_folder()
        for pdf in pdfs:
            if model_number in pdf['name']:
                result = (pdf['id'], pdf['name'])
                self._file_cache[model_number] = result
                return result
        
        logger.warning(f"No PDF found for model: {model_number}")
        return None
    
    def download_pdf(self, file_id: str, file_name: str) -> Optional[Path]:
        """
        Download a PDF file from Google Drive using direct link.
        
        Args:
            file_id: The Google Drive file ID
            file_name: The name to save the file as
            
        Returns:
            Path to the downloaded file, or None if download failed
        """
        try:
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            local_path = TEMP_DIR / file_name
            
            logger.info(f"Downloading PDF: {file_name} (ID: {file_id})")
            
            # Try direct download
            download_url = self.DOWNLOAD_URL.format(file_id=file_id)
            response = self.session.get(download_url, stream=True, timeout=60)
            
            # Handle virus scan confirmation page
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type:
                logger.info("Got confirmation page, retrying...")
                
                # Look for confirmation token
                confirm_token = None
                for key, value in response.cookies.items():
                    if 'download_warning' in key:
                        confirm_token = value
                        break
                
                if confirm_token:
                    download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm_token}"
                else:
                    download_url = self.CONFIRM_URL.format(file_id=file_id)
                
                response = self.session.get(download_url, stream=True, timeout=60)
            
            response.raise_for_status()
            
            # Save file
            with open(str(local_path), 'wb') as f:
                for chunk in response.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)
            
            # Verify PDF
            with open(str(local_path), 'rb') as f:
                header = f.read(5)
                if header != b'%PDF-':
                    logger.error("Downloaded file is not a valid PDF")
                    local_path.unlink()
                    return None
            
            file_size = local_path.stat().st_size
            logger.info(f"PDF downloaded: {local_path} ({file_size} bytes)")
            return local_path
            
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return None
    
    def download_pdf_by_model(self, model_number: str) -> Optional[Path]:
        """
        Search and download a PDF by model number.
        
        Args:
            model_number: The model number to search for
            
        Returns:
            Path to the downloaded PDF, or None if not found/download failed
        """
        result = self.search_pdf_by_model(model_number)
        
        if not result:
            return None
        
        file_id, file_name = result
        return self.download_pdf(file_id, file_name)


# Singleton instance
_drive_service = None


def get_drive_service() -> DriveService:
    """Get or create the Drive service singleton."""
    global _drive_service
    if _drive_service is None:
        _drive_service = DriveService()
    return _drive_service


def download_pdf_from_drive(model_number: str) -> Optional[Path]:
    """
    Download a PDF from Google Drive by model number.
    
    Args:
        model_number: The model number to search for (e.g., "270.2000")
        
    Returns:
        Path to the downloaded PDF file, or None if not found
    """
    service = get_drive_service()
    return service.download_pdf_by_model(model_number)
