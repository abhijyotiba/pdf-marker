# Part Diagram POC

Automatically highlight part numbers in product diagram PDFs and attach them to Freshdesk tickets.

## Features

- Receives Freshdesk webhooks for ticket updates
- Extracts model and part numbers using regex
- Downloads PDF diagrams from Google Drive
- Locates and highlights the part number in the PDF
- Uploads the highlighted image back to the Freshdesk ticket

## Prerequisites

- Python 3.9+
- Google Drive folder with "Anyone with link" access
- Freshdesk account with API access
- ngrok (for local testing)

## Setup

### 1. Install Dependencies

```bash
cd part-diagram-poc
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Google Drive Configuration
GOOGLE_DRIVE_FOLDER_ID=your-folder-id-here
GOOGLE_API_KEY=your-google-api-key-here

# Freshdesk Configuration (optional for local testing)
FRESHDESK_DOMAIN=your-freshdesk-subdomain
FRESHDESK_API_KEY=your-freshdesk-api-key
```

### 3. Get Google API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Enable the **Google Drive API**
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > API Key**
6. Copy the API key to `.env`
7. Make sure your Drive folder has "Anyone with link" access

### 4. Get Drive Folder ID

From your Drive folder URL:
`https://drive.google.com/drive/folders/YOUR_FOLDER_ID_HERE`

Copy the folder ID to `.env`

### 5. Configure Freshdesk (Optional)

Add to `.env`:
```env
FRESHDESK_DOMAIN=yourcompany
FRESHDESK_API_KEY=your-api-key
```

### 6. Verify Setup

```bash
python test_drive.py
```

This will list all PDFs in your Drive folder.

## Running the Server

### Local Testing (without Freshdesk)

```bash
python test_local.py 230.1000 230.1000-1214
```

This downloads the PDF, highlights the part, and opens the image.

### Development Server

```bash
python app.py
```

Server starts at `http://localhost:5000`

### Using ngrok (for Freshdesk webhooks)

```bash
ngrok http 5000
```

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) for the Freshdesk webhook.

### Production

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Freshdesk Webhook Setup

1. Go to Freshdesk Admin > Automations > Ticket Updates
2. Create a new rule:
   - **Condition**: When a ticket is Updated (or when tag "generate-diagram" is added)
   - **Action**: Trigger webhook
3. Configure webhook:
   - **URL**: `https://your-server.com/webhook`
   - **Method**: POST
   - **Encoding**: JSON
   - **Content**: Include ticket_id, ticket_description, ticket_subject

## API Endpoints

### `GET /`
Health check endpoint.

### `POST /webhook`
Main Freshdesk webhook endpoint. Receives ticket data and processes diagram requests.

**Expected Payload:**
```json
{
  "ticket_id": 12345,
  "ticket_description": "I need part 160.2400-18001 for model 270.2000",
  "ticket_subject": "Part request"
}
```

### `POST /test`
Manual testing endpoint (no Freshdesk required).

**Request:**
```json
{
  "ticket_id": 99999,
  "model": "270.2000",
  "part": "160.2400-18001"
}
```

### `GET /list-pdfs`
Debug endpoint to list all PDFs in the configured Google Drive folder.

## Testing

### Test 1: List PDFs
```bash
curl http://localhost:5000/list-pdfs
```

### Test 2: Manual Processing
```bash
curl -X POST http://localhost:5000/test ^
  -H "Content-Type: application/json" ^
  -d "{\"ticket_id\": 99999, \"model\": \"270.2000\", \"part\": \"160.2400-18001\"}"
```

### Test 3: Simulate Webhook
```bash
curl -X POST http://localhost:5000/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"ticket_id\": 12345, \"ticket_description\": \"Model 270.2000 part 160.2400-18001\", \"ticket_subject\": \"Part inquiry\"}"
```

## File Structure

```
part-diagram-poc/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── drive_service.py       # Google Drive integration (public access)
├── pdf_engine.py          # PDF processing and highlighting
├── freshdesk_service.py   # Freshdesk API integration
├── requirements.txt       # Python dependencies
├── test_drive.py          # Helper to test Drive access & get file IDs
├── temp/                  # Temporary files (auto-created)
└── README.md              # This file
```

## Model & Part Number Formats

The system expects:
- **Model Number**: `XXX.XXXX` (e.g., `270.2000`)
- **Part Number**: `XXX.XXXX-XXXXX` (e.g., `160.2400-18001`)

Modify regex patterns in `config.py` if your format differs.

## Troubleshooting

### "PDF not found"
- Check that the PDF filename contains the model number
- Verify the Drive folder is shared with the service account
- Run `GET /list-pdfs` to see available files

### "Part not found in diagram"
- The part number text must exist in the PDF
- Check if the PDF text is searchable (not just image)

### Google Drive errors
- Verify `service_account.json` is in the project directory
- Ensure Drive API is enabled in Google Cloud Console
- Check that folder is shared with service account email

### Freshdesk errors
- Verify API key is correct
- Check domain format (just subdomain, not full URL)
- Ensure API access is enabled on your Freshdesk plan

## Logs

Logs are written to:
- Console (stdout)
- `app.log` file in the project directory

## License

Internal POC - Not for distribution.
