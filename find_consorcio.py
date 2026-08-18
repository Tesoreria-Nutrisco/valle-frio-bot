#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH, DRIVE_FOLDER_ID_CARTOLAS

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

# Obtener ID de la carpeta 'consorcio'
query = f"parents='{DRIVE_FOLDER_ID_CARTOLAS}' and name='consorcio' and mimeType='application/vnd.google-apps.folder' and trashed=false"

results = drive.files().list(
    q=query,
    spaces='drive',
    pageSize=10,
    fields='files(id, name)'
).execute()

files = results.get('files', [])
if files:
    print(files[0]['id'])
else:
    print('Carpeta consorcio no encontrada')
