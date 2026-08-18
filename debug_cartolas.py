#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH, DRIVE_FOLDER_ID_CARTOLAS, TEAM_DRIVE_ID

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

query = f"parents='{DRIVE_FOLDER_ID_CARTOLAS}' and trashed=false"

results = drive.files().list(
    corpora='drive',
    driveId=TEAM_DRIVE_ID,
    includeItemsFromAllDrives=True,
    supportsAllDrives=True,
    q=query,
    spaces='drive',
    pageSize=50,
    orderBy='modifiedTime desc',
    fields='files(id, name, mimeType, modifiedTime)'
).execute()

files = results.get('files', [])
print(f'Total archivos en DRIVE_FOLDER_ID_CARTOLAS: {len(files)}\n')
for f in files:
    print(f"{f['name']} | {f['mimeType']} | {f.get('modifiedTime', 'N/A')}")
