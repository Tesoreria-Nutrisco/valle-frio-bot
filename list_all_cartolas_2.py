#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# Buscar TODOS los archivos cartola
query = "name contains 'cartola_consorcio' and trashed=false and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=100,
    orderBy='modifiedTime desc',
    fields='files(id, name, modifiedTime)'
).execute()

files = results.get('files', [])
print(f'Total cartolas encontradas: {len(files)}\n')
print('Cartolas (más recientes primero):')
for f in files:
    print(f"  {f['name']} | {f['modifiedTime'][:10]}")
