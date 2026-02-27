# PDF Part Diagram Highlighting Service - Implementation Guide

## Overview

This service automatically locates and highlights part numbers in PDF technical diagrams. It's designed to be integrated into AI agentic workflows, receiving requests via webhooks or direct API calls and returning highlighted diagram images.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Core Components](#core-components)
3. [Dependencies](#dependencies)
4. [Environment Setup](#environment-setup)
5. [Configuration](#configuration)
6. [API Endpoints](#api-endpoints)
7. [Integration Patterns](#integration-patterns)
8. [Critical Implementation Details](#critical-implementation-details)
9. [Common Mistakes to Avoid](#common-mistakes-to-avoid)
10. [Testing Strategy](#testing-strategy)
11. [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AI AGENTIC WORKFLOW                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          ENTRY POINTS                                    │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐       │
│  │ Freshdesk       │   │ Direct API      │   │ Local Test      │       │
│  │ Webhook         │   │ /test endpoint  │   │ CLI             │       │
│  │ /webhook        │   │                 │   │ test_local.py   │       │
│  └────────┬────────┘   └────────┬────────┘   └────────┬────────┘       │
└───────────┼──────────────────────┼──────────────────────┼───────────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          app.py - Flask Application                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ extract_model_and_part(text) → (model_number, part_number)      │   │
│  │ process_diagram_request(ticket_id, description, subject)        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  drive_service.py │   │  pdf_engine.py    │   │freshdesk_service.py│
│                   │   │                   │   │                   │
│ • Search PDF by   │   │ • Find part text  │   │ • Get ticket      │
│   model number    │   │ • Render PDF page │   │ • Add notes       │
│ • Download PDF    │   │ • Draw highlight  │   │ • Attach images   │
│ • List all PDFs   │   │ • Convert coords  │   │ • Post replies    │
└───────────────────┘   └───────────────────┘   └───────────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  Google Drive     │   │  PDF Files        │   │  Freshdesk API    │
│  (Public Folder   │   │  (Technical       │   │  (Ticketing       │
│   with API Key)   │   │   Diagrams)       │   │   System)         │
└───────────────────┘   └───────────────────┘   └───────────────────┘
```

### Data Flow

```
1. Request arrives (webhook/API) with text containing model/part numbers
                    ↓
2. extract_model_and_part() → extracts using regex patterns
   Model: XXX.XXXX (e.g., 270.2000)
   Part:  XXX.XXXX-XXXXX (e.g., 160.2400-18001)
                    ↓
3. drive_service.download_pdf_from_drive(model_number)
   → Searches Google Drive for PDF matching model
   → Downloads to /temp/ directory
                    ↓
4. pdf_engine.highlight_part_in_pdf(pdf_path, part_number)
   a. Find part text location in PDF (returns page + bbox)
   b. Render PDF page to PNG at 300 DPI
   c. Transform PDF coordinates → pixel coordinates (CRITICAL)
   d. Draw highlight rectangle + arrow
   e. Save to /output/ directory
                    ↓
5. freshdesk_service.add_highlighted_diagram()
   → Attaches PNG to ticket as private note
                    ↓
6. Cleanup temp files
```

---

## Core Components

### 1. `config.py` - Configuration Management

Centralizes all configuration with environment variable loading.

```python
# Key configurations:
GOOGLE_DRIVE_CONFIG = {
    "FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID"),
    "API_KEY": os.getenv("GOOGLE_API_KEY"),
}

FRESHDESK_CONFIG = {
    "DOMAIN": os.getenv("FRESHDESK_DOMAIN"),
    "API_KEY": os.getenv("FRESHDESK_API_KEY"),
}

PDF_CONFIG = {
    "RENDER_DPI": 300,      # Output image resolution
    "PDF_BASE_DPI": 72,     # Standard PDF DPI
    "HIGHLIGHT_COLOR": "red",
    "HIGHLIGHT_WIDTH": 4,
    "HIGHLIGHT_PADDING": 5,
}

REGEX_PATTERNS = {
    "MODEL": r"(?:\d{3}\.\d{4}[A-Z]?|K\.\d{4})",
    "PART": r"\d{3}\.\d{4}-\d{4,5}",
}
```

### 2. `drive_service.py` - Google Drive Integration

Handles PDF retrieval from publicly shared Google Drive folder.

**Key Methods:**
- `list_pdfs_in_folder()` - Lists all PDFs using API or manual mapping
- `search_pdf_by_model(model_number)` - Finds PDF by model number
- `download_pdf(file_id, file_name)` - Downloads PDF to temp directory

**Supports two modes:**
1. **API Key Mode** (recommended): Uses Google Drive API with API key
2. **Manual Mapping Mode**: Uses hardcoded file ID mapping

### 3. `pdf_engine.py` - PDF Processing Engine

The core processing component that finds and highlights parts.

**Key Classes:**
- `PartLocation` - Dataclass holding page_index, bbox, and text
- `PDFEngine` - Main processing class with rendering and highlighting

**Pipeline:**
1. `find_part_in_pdf()` - Locates part number using `page.search_for()`
2. `render_page_to_image()` - Converts PDF page to PNG using PyMuPDF
3. `_bbox_to_pixel_rect()` - **CRITICAL**: Coordinate transformation
4. `draw_highlight()` - Draws rectangle and arrow using Pillow

### 4. `freshdesk_service.py` - Freshdesk Integration

Handles all Freshdesk API interactions.

**Key Methods:**
- `get_ticket()` - Fetches ticket details
- `add_private_note()` - Adds note with optional attachment
- `add_reply()` - Sends public reply with attachment
- `get_ticket_conversations()` - Gets ticket history

### 5. `app.py` - Flask Application

REST API server with webhook handling.

**Endpoints:**
- `GET /` - Health check
- `POST /webhook` - Freshdesk webhook handler
- `POST /test` - Manual testing endpoint
- `GET /list-pdfs` - Debug endpoint to list available PDFs

---

## Dependencies

### requirements.txt

```txt
# Web Framework
Flask>=3.0.0
Werkzeug>=3.0.1

# Environment variables
python-dotenv>=1.0.0

# PDF Processing (use latest for Python 3.13 compatibility)
PyMuPDF>=1.24.0

# Image Processing
Pillow>=10.1.0

# HTTP Requests
requests>=2.31.0

# Production Server (optional)
gunicorn>=21.2.0
```

### System Requirements
- Python 3.10+ (tested with 3.13)
- ~500MB RAM minimum
- Disk space for temp PDF files

### Installation

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Environment Setup

### .env File

Create a `.env` file in the project root:

```env
# Google Drive Configuration
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
GOOGLE_API_KEY=your_api_key_here

# Freshdesk Configuration
FRESHDESK_DOMAIN=yourcompany
FRESHDESK_API_KEY=your_freshdesk_api_key

# Server Configuration
HOST=0.0.0.0
PORT=5000
DEBUG=True
LOG_LEVEL=INFO
```

### Getting Google Drive Folder ID

1. Open Google Drive and navigate to your PDF folder
2. The URL will be: `https://drive.google.com/drive/folders/FOLDER_ID`
3. Copy the `FOLDER_ID` portion

### Setting Up Google API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Drive API
4. Go to Credentials → Create Credentials → API Key
5. **Important**: Restrict the API key to Google Drive API only
6. Make sure the Drive folder is publicly shared (view access)

### Getting Freshdesk API Key

1. Log into Freshdesk as admin
2. Click profile icon → Profile Settings
3. Find API Key on the right sidebar
4. Your domain is the subdomain: `yourcompany.freshdesk.com`

---

## Configuration

### PDF Processing Settings

```python
PDF_CONFIG = {
    "RENDER_DPI": 300,          # Higher = better quality, larger file
    "PDF_BASE_DPI": 72,         # Standard, don't change
    "HIGHLIGHT_COLOR": "red",   # Color name or hex
    "HIGHLIGHT_WIDTH": 4,       # Line thickness in pixels
    "HIGHLIGHT_PADDING": 5,     # Space around text
}
```

### Regex Patterns

Customize these for your part/model number formats:

```python
REGEX_PATTERNS = {
    # Model: XXX.XXXX or K.XXXX
    "MODEL": r"(?:\d{3}\.\d{4}[A-Z]?|K\.\d{4})",
    
    # Part: XXX.XXXX-XXXX or XXX.XXXX-XXXXX
    "PART": r"\d{3}\.\d{4}-\d{4,5}",
}
```

---

## API Endpoints

### Health Check
```http
GET /
Response: {"status": "healthy", "service": "Part Diagram POC"}
```

### Freshdesk Webhook
```http
POST /webhook
Content-Type: application/json

{
    "ticket_id": 12345,
    "ticket_description": "Need part 230.1000-1214 for model 230.1000",
    "ticket_subject": "Part request"
}
```

### Test Endpoint
```http
POST /test
Content-Type: application/json

{
    "ticket_id": 99999,
    "model": "230.1000",
    "part": "230.1000-1214"
}
```

### List PDFs (Debug)
```http
GET /list-pdfs
Response: {"count": 15, "files": [...]}
```

---

## Integration Patterns

### Pattern 1: Direct API Integration (Recommended for AI Agents)

```python
import requests

def highlight_part_diagram(model: str, part: str) -> dict:
    """Call the highlighting service from an AI agent."""
    response = requests.post(
        "http://localhost:5000/test",
        json={
            "ticket_id": "agent_request_001",
            "model": model,
            "part": part
        },
        timeout=60
    )
    return response.json()
```

### Pattern 2: Webhook Integration (Freshdesk Automation)

Configure in Freshdesk Admin → Automations:
- Trigger: Ticket created with specific conditions
- Action: Trigger webhook to your service URL

### Pattern 3: As a Python Module

```python
from pdf_engine import highlight_part_in_pdf
from drive_service import download_pdf_from_drive

def process_part_request(model: str, part: str) -> str:
    """Use as a library in your AI agent code."""
    
    # Download PDF
    pdf_path = download_pdf_from_drive(model)
    if not pdf_path:
        return "PDF not found"
    
    # Generate highlighted image
    output_path = highlight_part_in_pdf(pdf_path, part, "output_id")
    if not output_path:
        return "Part not found in PDF"
    
    return str(output_path)
```

### Pattern 4: Standalone Function for LangChain/CrewAI Tools

```python
from langchain.tools import tool
from pathlib import Path

@tool
def find_and_highlight_part(model_number: str, part_number: str) -> str:
    """
    Finds a part in a technical diagram and returns a highlighted image.
    
    Args:
        model_number: The model number (e.g., "270.2000")
        part_number: The part number to highlight (e.g., "160.2400-18001")
    
    Returns:
        Path to the highlighted PNG image, or error message
    """
    from drive_service import download_pdf_from_drive
    from pdf_engine import highlight_part_in_pdf
    
    pdf_path = download_pdf_from_drive(model_number)
    if not pdf_path:
        return f"Error: PDF for model {model_number} not found"
    
    output_path = highlight_part_in_pdf(
        pdf_path, 
        part_number, 
        f"{model_number}_{part_number}"
    )
    
    if output_path:
        return f"Highlighted image saved to: {output_path}"
    return f"Error: Part {part_number} not found in PDF"
```

---

## Critical Implementation Details

### 1. Coordinate System Transformation (MOST IMPORTANT)

**The Problem**: PDF coordinates are in "points" (72 DPI), but rendered images are at 300 DPI. Additionally, PDFs can have rotation, crop boxes, and other transformations.

**WRONG Approach** (causes misaligned highlights):
```python
# ❌ DON'T DO THIS - breaks on rotated/cropped PDFs
scale = render_dpi / pdf_dpi  # 300/72 = 4.167
pixel_x = pdf_x * scale
pixel_y = pdf_y * scale
```

**CORRECT Approach** (use matrix transformation):
```python
# ✅ ALWAYS USE THIS - handles all edge cases
mat = fitz.Matrix(scale_factor, scale_factor)

# Render page with matrix
pixmap = page.get_pixmap(matrix=mat)

# Transform coordinates with SAME matrix  
pdf_rect = fitz.Rect(x0, y0, x1, y1)
pixel_rect = pdf_rect * mat  # Matrix multiplication handles rotation/crop
```

### 2. Part Location Strategy

Many PDFs have the part number appearing multiple times:
- In the diagram (what we want)
- In title blocks, headers, or footers (what we DON'T want)

**Solution**: Filter by position on page
```python
def _is_in_diagram_area(self, bbox, page_rect, margin_fraction=0.05):
    """Skip matches in top/bottom 5% of page (header/footer zones)."""
    page_h = page_rect.height
    margin = page_h * margin_fraction
    _, y0, _, y1 = bbox
    return y0 > margin and y1 < (page_h - margin)
```

### 3. Handling Large PDFs (Virus Scan Confirmation)

Google Drive shows a confirmation page for large files:
```python
# Handle virus scan confirmation page
if 'text/html' in content_type:
    # Look for confirmation token in cookies
    confirm_token = None
    for key, value in response.cookies.items():
        if 'download_warning' in key:
            confirm_token = value
            break
    # Retry with confirmation
    download_url = f"{url}&confirm={confirm_token}"
```

### 4. Text Search Methods

PyMuPDF provides multiple text search methods:
```python
# Primary method - most reliable
instances = page.search_for(part_number)  # Returns list of fitz.Rect

# Alternative - get all text with positions
blocks = page.get_text("dict")["blocks"]
# Then search manually for better control
```

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Manual Coordinate Scaling

**Wrong:**
```python
pixel_x = pdf_x * (render_dpi / 72)
```

**Right:**
```python
pixel_rect = fitz.Rect(pdf_bbox) * render_matrix
```

**Why**: Manual scaling ignores page rotation (`/Rotate`), crop boxes, and media box offsets. The matrix handles all of these.

---

### ❌ Mistake 2: Using Different Matrices for Render and Transform

**Wrong:**
```python
pixmap = page.get_pixmap(matrix=fitz.Matrix(4, 4))
# Later...
rect = fitz.Rect(bbox) * fitz.Matrix(4.167, 4.167)  # Different values!
```

**Right:**
```python
mat = fitz.Matrix(scale_factor, scale_factor)  # Define once
pixmap = page.get_pixmap(matrix=mat)           # Use for render
pixel_rect = fitz.Rect(bbox) * mat             # Use SAME for transform
```

---

### ❌ Mistake 3: Not Handling Header/Footer Text Matches

**Wrong:**
```python
matches = page.search_for(part_number)
return matches[0]  # First match might be in title block!
```

**Right:**
```python
matches = page.search_for(part_number)
for match in matches:
    if is_in_diagram_area(match, page.rect):
        return match  # Prefer diagram area match
return matches[0]  # Fallback to first if all in header/footer
```

---

### ❌ Mistake 4: Hardcoding File Paths

**Wrong:**
```python
pdf_path = "C:/Users/john/project/temp/file.pdf"
```

**Right:**
```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
```

---

### ❌ Mistake 5: Forgetting to Close PDF Documents

**Wrong:**
```python
doc = fitz.open(pdf_path)
page = doc[0]
# Process...
# Forgot to close! File stays locked
```

**Right:**
```python
doc = fitz.open(pdf_path)
try:
    page = doc[0]
    # Process...
finally:
    doc.close()

# Or use context manager:
with fitz.open(pdf_path) as doc:
    page = doc[0]
    # Process...
```

---

### ❌ Mistake 6: Not Handling Multiple Response Formats

Freshdesk webhooks can have different payload structures:

**Wrong:**
```python
ticket_id = data["ticket_id"]  # KeyError if different format
```

**Right:**
```python
ticket_id = (
    data.get("ticket_id") or 
    data.get("freshdesk_webhook", {}).get("ticket_id") or
    data.get("id")
)
```

---

### ❌ Mistake 7: Synchronous File Downloads Blocking Server

For production, consider async downloads:
```python
# Use threading or async for large files
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=3)
future = executor.submit(download_pdf, file_id)
```

---

### ❌ Mistake 8: Not Cleaning Up Temp Files

**Wrong:**
```python
# Process completes, temp files accumulate forever
```

**Right:**
```python
def cleanup_temp_files(ticket_id: str):
    """Clean up after processing."""
    # Clean specific files
    for f in TEMP_DIR.glob(f"*{ticket_id}*"):
        f.unlink()
    
    # Clean old files (over 1 hour)
    import time
    for f in TEMP_DIR.glob("*.pdf"):
        if time.time() - f.stat().st_mtime > 3600:
            f.unlink()
```

---

## Testing Strategy

### Local Testing (Without External Services)

```python
# test_local.py
python test_local.py <model_number> <part_number>

# Example:
python test_local.py 230.1000 230.1000-1214
```

### Diagnostic Functions

```python
from pdf_engine import get_pdf_engine

engine = get_pdf_engine()

# Dump all text with coordinates
engine.dump_text_blocks(pdf_path, page_index=0)

# Show all matches with pixel coordinates
engine.diagnose_part(pdf_path, "230.1000-1214")
```

### Testing Flow

1. **Test Drive Connection**: `GET /list-pdfs`
2. **Test Single Part**: `POST /test` with known model/part
3. **Verify Coordinates**: Use `diagnose_part()` if highlight is misaligned
4. **Test Full Webhook**: Use Freshdesk sandbox or ngrok

---

## Troubleshooting

### Issue: Highlight Appears in Wrong Location

**Cause**: Coordinate transformation mismatch

**Solution**:
1. Run `engine.diagnose_part(pdf_path, part_number)`
2. Compare PDF bbox vs pixel bbox
3. Ensure both render and transform use the same `fitz.Matrix`

### Issue: Part Not Found in PDF

**Possible Causes**:
1. Part number is an outline/vector graphic (not searchable text)
2. OCR text has errors
3. Regex pattern doesn't match

**Solution**:
1. Run `engine.dump_text_blocks(pdf_path)` to see actual text
2. Try partial search: `page.search_for("1214")` instead of full part number

### Issue: PDF Download Fails

**Solutions**:
1. Verify folder is publicly shared (at least view access)
2. Check API key is enabled for Drive API
3. Test direct download URL in browser

### Issue: Freshdesk Attachment Fails

**Solutions**:
1. Verify API key has ticket write permissions
2. Check file exists before upload
3. Ensure content-type is correct (`image/png`)

---

## Production Deployment Checklist

- [ ] Set `DEBUG=False` in .env
- [ ] Use gunicorn instead of Flask dev server
- [ ] Set up HTTPS (use nginx/cloudflare)
- [ ] Configure proper logging (rotate logs)
- [ ] Set up monitoring (uptime checks)
- [ ] Implement rate limiting
- [ ] Add authentication to test endpoints
- [ ] Set up automated cleanup for temp files
- [ ] Configure error alerting (Sentry, etc.)
- [ ] Test with realistic load

### Production Command

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## Quick Reference

### File Structure
```
part-diagram-poc/
├── app.py              # Flask application, endpoints
├── config.py           # All configuration
├── drive_service.py    # Google Drive operations
├── pdf_engine.py       # PDF processing core
├── freshdesk_service.py# Freshdesk API
├── test_local.py       # Local testing CLI
├── requirements.txt    # Dependencies
├── .env                # Secrets (not in git)
├── temp/               # Downloaded PDFs
└── output/             # Generated images
```

### Key Functions
```python
# Download PDF
pdf_path = download_pdf_from_drive(model_number)

# Generate highlight
output_path = highlight_part_in_pdf(pdf_path, part_number, ticket_id)

# Attach to ticket
success = add_highlighted_diagram(ticket_id, output_path, part_number)
```

### Environment Variables
```env
GOOGLE_DRIVE_FOLDER_ID=<folder_id>
GOOGLE_API_KEY=<api_key>
FRESHDESK_DOMAIN=<company>
FRESHDESK_API_KEY=<api_key>
PORT=5000
DEBUG=True
```

---

*Last Updated: February 2026*
