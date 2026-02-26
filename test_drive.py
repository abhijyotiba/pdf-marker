"""
Test script to verify Drive service and extract file IDs

Run this to:
1. Test if Drive folder access works
2. Get file IDs for manual mapping (if API key is not set)
"""
import sys
sys.path.insert(0, '.')

import re
import requests

from config import GOOGLE_DRIVE_CONFIG

FOLDER_ID = GOOGLE_DRIVE_CONFIG["FOLDER_ID"]
API_KEY = GOOGLE_DRIVE_CONFIG.get("API_KEY", "")

print("=" * 60)
print("Google Drive File ID Extractor")
print("=" * 60)
print(f"\nFolder ID: {FOLDER_ID}")
print(f"Folder URL: https://drive.google.com/drive/folders/{FOLDER_ID}")

if API_KEY:
    print(f"API Key: {'*' * 20}... (configured)")
    
    # Use API to list files
    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        'q': f"'{FOLDER_ID}' in parents and mimeType='application/pdf' and trashed=false",
        'key': API_KEY,
        'fields': 'files(id,name,size)',
        'pageSize': 100
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        files = data.get('files', [])
        
        print(f"\nFound {len(files)} PDF files:\n")
        print("Add these to FILE_MAPPING in config.py:\n")
        print('"FILE_MAPPING": {')
        
        for f in files:
            name = f['name']
            file_id = f['id']
            # Try to extract model number
            model_match = re.search(r'\d{3}\.\d{4}', name)
            if model_match:
                model = model_match.group()
                print(f'    "{model}": "{file_id}",  # {name}')
            else:
                print(f'    # "{name}": "{file_id}",')
        
        print('},')
        
        # Test download of first file
        if files:
            print("\n" + "=" * 60)
            print("Testing download of first PDF...")
            first = files[0]
            download_url = f"https://drive.google.com/uc?export=download&id={first['id']}"
            resp = requests.get(download_url, stream=True, timeout=30)
            
            # Check if it's a PDF or HTML (confirmation page)
            content_type = resp.headers.get('Content-Type', '')
            if 'application/pdf' in content_type:
                print(f"SUCCESS! Direct download works for: {first['name']}")
            elif 'text/html' in content_type:
                # Try with confirm
                download_url = f"https://drive.google.com/uc?export=download&id={first['id']}&confirm=t"
                resp = requests.get(download_url, stream=True, timeout=30)
                content = resp.content[:100]
                if content.startswith(b'%PDF'):
                    print(f"SUCCESS! Download works (with confirm) for: {first['name']}")
                else:
                    print("Download may need additional handling")
            
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure:")
        print("1. Your API key is valid")
        print("2. Google Drive API is enabled in your GCP project")
        print("3. The folder is publicly accessible")

else:
    print("\nNo API Key configured.")
    print("\nYou have two options:\n")
    print("OPTION 1: Get an API Key (recommended)")
    print("-" * 40)
    print("1. Go to: https://console.cloud.google.com/apis/credentials")
    print("2. Create a new API Key")
    print("3. Enable 'Google Drive API' in your project")
    print("4. Add the API key to config.py: GOOGLE_DRIVE_CONFIG['API_KEY']")
    print("5. Run this script again\n")
    
    print("OPTION 2: Manual File Mapping")
    print("-" * 40)
    print("For each PDF in your Drive folder:")
    print("1. Right-click the file -> Share -> Copy link")
    print("2. Extract the file ID from the link:")
    print("   https://drive.google.com/file/d/FILE_ID_HERE/view")
    print("3. Add to FILE_MAPPING in config.py:")
    print('   "270.2000": "1abc123def456...",')
    print()
    
    # Test if folder is accessible
    print("Testing folder accessibility...")
    folder_url = f"https://drive.google.com/drive/folders/{FOLDER_ID}"
    try:
        resp = requests.get(folder_url, timeout=10)
        if resp.status_code == 200:
            print(f"Folder is accessible (HTTP {resp.status_code})")
        else:
            print(f"Folder may not be public (HTTP {resp.status_code})")
    except Exception as e:
        print(f"Could not access folder: {e}")
