#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

consorcio_id = '1u1QpeOnDQ65213UC_drQvB470EosNR3z'

# Listar TODO sin filtros
query = f"parents='{consorcio_id}' and trashed=false"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=100,
    fields='files(id, name, mimeType)'
).execute()

files = results.get('files', [])
print(f'Items en carpeta consorcio ({len(files)}):')
for f in files:
    print(f"  {f['name']} | {f['mimeType']} | ID: {f['id']}")

    # Si es carpeta, listar adentro
    if 'folder' in f['mimeType']:
        query2 = f"parents='{f['id']}' and trashed=false"
        results2 = drive.files().list(q=query2, spaces='drive', pageSize=100, fields='files(id, name, mimeType)').execute()
        files2 = results2.get('files', [])
        print(f"    -> {len(files2)} items adentro:")
        for f2 in files2[:15]:
            print(f"       {f2['name']} | {f2['mimeType']}")
