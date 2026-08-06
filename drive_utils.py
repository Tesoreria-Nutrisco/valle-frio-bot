import logging
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import CREDENTIALS_PATH, MODO_DRY_RUN

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    """Autentica con Google Drive usando service account."""
    credentials = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("drive", "v3", credentials=credentials)


def list_folder_contents(service, folder_id, name_filter=None, team_drive_id=None):
    """Lista archivos/carpetas en una carpeta, opcionalmente filtrados por nombre."""
    query = f"'{folder_id}' in parents and trashed=false"

    if name_filter:
        query += f" and name='{name_filter}'"

    params = {
        "q": query,
        "spaces": "drive",
        "fields": "files(id, name, mimeType)",
        "pageSize": 100,
    }

    # Si es una Shared Drive, agregar parámetros necesarios
    if team_drive_id:
        params["corpora"] = "teamDrive"
        params["driveId"] = team_drive_id
        params["includeTeamDriveItems"] = True
        params["supportsAllDrives"] = True

    results = service.files().list(**params).execute()
    return results.get("files", [])


def obtener_o_crear_carpeta(service, nombre, carpeta_padre_id, team_drive_id=None):
    """
    Busca una carpeta por nombre dentro del padre.
    Si existe, devuelve su ID.
    Si no existe, la crea y devuelve el ID nuevo.
    """
    logger.info(f"Buscando carpeta '{nombre}' dentro de {carpeta_padre_id}")

    if MODO_DRY_RUN:
        logger.info(f"[DRY RUN] Se habría buscado carpeta '{nombre}' en {carpeta_padre_id}")
        return f"dry-run-id-{nombre}"

    # Buscar (solo en modo real)
    items = list_folder_contents(service, carpeta_padre_id, nombre, team_drive_id)

    # Filtrar por tipo (solo carpetas)
    carpetas = [item for item in items if item["mimeType"] == "application/vnd.google-apps.folder"]

    if carpetas:
        folder_id = carpetas[0]["id"]
        logger.info(f"Carpeta '{nombre}' encontrada: {folder_id}")
        return folder_id

    # No existe, crear
    logger.info(f"Carpeta '{nombre}' no existe, creando...")

    file_metadata = {
        "name": nombre,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [carpeta_padre_id]
    }

    folder = service.files().create(
        body=file_metadata,
        fields="id",
        supportsTeamDrives=True,
        supportsAllDrives=True
    ).execute()
    folder_id = folder.get("id")
    logger.info(f"Carpeta '{nombre}' creada: {folder_id}")

    return folder_id


def get_carpeta_destino(service, raiz_folder_id, banco, fecha, team_drive_id=None):
    """
    Obtiene el ID de la carpeta destino siguiendo la estructura:
    raiz/banco/AAAA/MM/DD

    fecha es un datetime object
    """
    ano = str(fecha.year)
    mes = str(fecha.month).zfill(2)
    dia = str(fecha.day).zfill(2)

    # Nivel 1: banco
    folder_banco = obtener_o_crear_carpeta(service, banco, raiz_folder_id, team_drive_id)

    # Nivel 2: año
    folder_ano = obtener_o_crear_carpeta(service, ano, folder_banco, team_drive_id)

    # Nivel 3: mes
    folder_mes = obtener_o_crear_carpeta(service, mes, folder_ano, team_drive_id)

    # Nivel 4: día
    folder_dia = obtener_o_crear_carpeta(service, dia, folder_mes, team_drive_id)

    return folder_dia


def upload_file(service, file_path, folder_id, file_name=None):
    """
    Sube un archivo a una carpeta de Drive.
    Si file_name no se especifica, usa el nombre del archivo.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"Archivo no existe: {file_path}")
        raise FileNotFoundError(f"Archivo no existe: {file_path}")

    if not file_name:
        file_name = file_path.name

    logger.info(f"Subiendo {file_name} a Drive (folder: {folder_id})")

    if MODO_DRY_RUN:
        logger.info(f"[DRY RUN] Se habría subido {file_name} a {folder_id}")
        return f"dry-run-{file_name}"

    file_metadata = {
        "name": file_name,
        "parents": [folder_id]
    }

    media = MediaFileUpload(str(file_path), resumable=True)

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsTeamDrives=True,
        supportsAllDrives=True
    ).execute()

    file_id = file.get("id")
    logger.info(f"Archivo '{file_name}' subido exitosamente: {file_id}")

    return file_id
