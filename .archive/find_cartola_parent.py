#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# Encontrar UNA cartola y ver su estructura de padres
query = "name contains 'cartola_consorcio' and trashed=false and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=1,
    fields='files(id, name, parents, webViewLink)'
).execute()

files = results.get('files', [])
if files:
    f = files[0]
    print(f"Archivo: {f['name']}")
    print(f"ID: {f['id']}")
    print(f"Parents: {f['parents']}")
    print(f"Link: {f['webViewLink']}")

    # Seguir la cadena de padres
    parent_id = f['parents'][0]
    level = 0
    print(f"\nCadena de carpetas:")
    while parent_id and level < 10:
        results2 = drive.files().list(
            q=f"trashed=false",
            pageSize=1,
            fields='files(id, name, parents)',
            pageToken=None
        ).execute()

        # Buscar el parent específico
        results3 = drive.files().get(fileId=parent_id, fields='id, name, parents').execute()
        print(f"  {'  ' * level}├─ {results3['name']} (ID: {parent_id})")

        parent_id = results3.get('parents', [None])[0] if results3.get('parents') else None
        level += 1
else:
    print("No se encontraron cartolas")
