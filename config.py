"""
Configuration settings for Part Diagram POC
All sensitive credentials are loaded from .env file
"""
import os
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Temp directory for downloaded PDFs (intermediate files)
TEMP_DIR = BASE_DIR / "temp"

# Output directory for highlighted images
OUTPUT_DIR = BASE_DIR / "output"

# Google Drive Configuration
GOOGLE_DRIVE_CONFIG = {
    # Google Drive folder ID (from .env)
    "FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""),
    
    # Google API Key (from .env)
    "API_KEY": os.getenv("GOOGLE_API_KEY", ""),
    
    # File mapping is populated dynamically via API
    # Or can be set manually if API key is not available
    "FILE_MAPPING": {},
}

# Freshdesk Configuration
FRESHDESK_CONFIG = {
    "DOMAIN": os.getenv("FRESHDESK_DOMAIN", ""),
    "API_KEY": os.getenv("FRESHDESK_API_KEY", ""),
}

# PDF Processing Configuration
PDF_CONFIG = {
    "RENDER_DPI": 300,
    "PDF_BASE_DPI": 72,
    "HIGHLIGHT_COLOR": "red",
    "HIGHLIGHT_WIDTH": 4,
    "HIGHLIGHT_PADDING": 5,
}

# Regex patterns for extracting model and part numbers
REGEX_PATTERNS = {
    # Model number pattern: XXX.XXXX (e.g., 270.2000) or K.XXXX (e.g., K.1390)
    "MODEL": r"(?:\d{3}\.\d{4}[A-Z]?|K\.\d{4})",
    
    # Part number pattern: XXX.XXXX-XXXX (e.g., 230.1000-1214)
    "PART": r"\d{3}\.\d{4}-\d{4,5}",
}

# Server Configuration
SERVER_CONFIG = {
    "HOST": os.getenv("HOST", "0.0.0.0"),
    "PORT": int(os.getenv("PORT", "5000")),
    "DEBUG": os.getenv("DEBUG", "True").lower() == "true",
}

# Logging Configuration
LOGGING_CONFIG = {
    "LOG_FILE": str(BASE_DIR / "app.log"),
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
}
