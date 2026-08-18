#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# Buscar TODOS los archivos que contengan "cartola" en el nombre
query = "name contains 'cartola' and trashed=false and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=100,
    orderBy='modifiedTime desc',
    fields='files(id, name, parents, modifiedTime, webViewLink)'
).execute()

files = results.get('files', [])
print(f'Archivos cartola encontrados: {len(files)}\n')

for i, f in enumerate(files[:10], 1):
    print(f"{i}. {f['name']}")
    print(f"   ID: {f['id']}")
    print(f"   Modificado: {f.get('modifiedTime', 'N/A')}")
    print(f"   Parents: {f.get('parents', ['N/A'])}")
    print()
