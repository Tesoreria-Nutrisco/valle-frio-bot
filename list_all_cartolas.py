#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH, DRIVE_FOLDER_ID_CARTOLAS, TEAM_DRIVE_ID

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# Listar TODOS los archivos, incluyendo carpetas
query = f"parents='{DRIVE_FOLDER_ID_CARTOLAS}' and trashed=false"

results = drive.files().list(
    corpora='drive',
    driveId=TEAM_DRIVE_ID,
    includeItemsFromAllDrives=True,
    supportsAllDrives=True,
    q=query,
    spaces='drive',
    pageSize=50,
    fields='files(id, name, mimeType, parents)'
).execute()

files = results.get('files', [])
print(f'Total items: {len(files)}\n')
for f in files:
    is_folder = 'folder' in f['mimeType']
    print(f"[{'FOLDER' if is_folder else 'FILE'}] {f['name']} | ID: {f['id']}")

    # Si es carpeta, listar lo que hay dentro
    if is_folder:
        query2 = f"parents='{f['id']}' and trashed=false"
        results2 = drive.files().list(
            q=query2,
            spaces='drive',
            pageSize=50,
            fields='files(id, name, mimeType, modifiedTime)'
        ).execute()
        files2 = results2.get('files', [])
        print(f"    -> Contiene {len(files2)} items:")
        for f2 in files2[:10]:  # Mostrar solo los primeros 10
            print(f"       - {f2['name']} | {f2['mimeType']} | {f2.get('modifiedTime', 'N/A')}")
        if len(files2) > 10:
            print(f"       ... y {len(files2) - 10} más")
