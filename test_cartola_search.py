#!/usr/bin/env python3
import sys
sys.path.insert(0, 'bot2')

from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import GOOGLE_DRIVE_CREDENTIALS_PATH, DRIVE_FOLDER_ID_CARTOLAS, TEAM_DRIVE_ID

scopes = ['https://www.googleapis.com/auth/drive']
credentials = Credentials.from_service_account_file(GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes)
drive = build('drive', 'v3', credentials=credentials)

fecha_desde = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

print(f"DRIVE_FOLDER_ID_CARTOLAS = {DRIVE_FOLDER_ID_CARTOLAS}")
print(f"Fecha desde: {fecha_desde}")
print()

# Recrear el query de cartola_cleaner.py
query = (
    f"parents='{DRIVE_FOLDER_ID_CARTOLAS}' "
    f"and name contains 'cartola' "
    f"and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
    f"and modifiedTime > '{fecha_desde}' "
    f"and trashed=false"
)

print(f"Query: {query}\n")

results = drive.files().list(
    corpora="drive",
    driveId=TEAM_DRIVE_ID,
    includeItemsFromAllDrives=True,
    supportsAllDrives=True,
    q=query,
    spaces="drive",
    pageSize=10,
    orderBy="modifiedTime desc",
    fields="files(id, name, modifiedTime)"
).execute()

files = results.get("files", [])
print(f"Archivos encontrados: {len(files)}")
for f in files:
    print(f"  {f['name']} | {f['modifiedTime']}")
