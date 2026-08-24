#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# La carpeta consorcio tiene ID: 1u1QpeOnDQ65213UC_drQvB470EosNR3z
consorcio_id = '1u1QpeOnDQ65213UC_drQvB470EosNR3z'

# Buscar carpeta 2026
query = f"parents='{consorcio_id}' and name='2026' and mimeType='application/vnd.google-apps.folder' and trashed=false"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=10,
    fields='files(id, name)'
).execute()

files = results.get('files', [])
if files:
    folder_2026_id = files[0]['id']
    print(f'Carpeta 2026 ID: {folder_2026_id}')

    # Listar contenido de 2026
    query2 = f"parents='{folder_2026_id}' and trashed=false"
    results2 = drive.files().list(
        q=query2,
        spaces='drive',
        pageSize=50,
        fields='files(id, name, mimeType, modifiedTime)'
    ).execute()

    files2 = results2.get('files', [])
    print(f'\nContenido de 2026 ({len(files2)} items):')
    for f in files2[:20]:
        is_folder = 'folder' in f['mimeType']
        tipo = '[DIR]' if is_folder else '[FILE]'
        print(f'{tipo} {f["name"]} | {f.get("modifiedTime", "N/A")}')
else:
    print('Carpeta 2026 no encontrada')
