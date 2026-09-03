import logging
import os
import json
import base64
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import CREDENTIALS_PATH, MODO_DRY_RUN

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


async def get_drive_service():
    """Autentica con Google Drive usando Prefect Secret Block."""
    # ÚNICA OPCIÓN: Prefect Secret Block 'google-credentials-valle-frio'
    logger.info("=" * 80)
    logger.info("INTENTANDO CARGAR CREDENCIALES DESDE PREFECT SECRET BLOCK")
    logger.info("=" * 80)

    try:
        from prefect.blocks.system import Secret

        logger.info("Paso 1: Importando Secret Block")
        logger.info("Paso 2: Llamando await Secret.load('google-credentials-valle-frio')")
        secret_block = await Secret.load("google-credentials-valle-frio")
        logger.info(f"Paso 3: Secret Block cargado: {secret_block}")

        logger.info("Paso 4: Obteniendo valor con .get()")
        creds_json_str = secret_block.get()
        logger.info(f"Paso 5: Valor obtenido, type={type(creds_json_str)}")

        if not creds_json_str:
            raise ValueError("Secret Block vacío")

        # Secret Block devuelve dict directamente, no string JSON
        if isinstance(creds_json_str, str):
            logger.info("Paso 6: Parseando JSON (es string)")
            creds_dict = json.loads(creds_json_str)
        else:
            logger.info("Paso 6: Ya es dict, sin parse")
            creds_dict = creds_json_str

        logger.info(f"Paso 7: Credenciales listas, keys={list(creds_dict.keys())[:5]}")

        logger.info("Paso 8: Creando credenciales de Google")
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        logger.info("Paso 9: Credentials creadas")

        logger.info("Paso 10: Construyendo servicio Drive")
        service = build("drive", "v3", credentials=credentials)
        logger.info("✓ ÉXITO: Credenciales cargadas desde Secret Block")
        logger.info("=" * 80)
        return service

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"✗ ERROR CARGANDO SECRET BLOCK")
        logger.error(f"Tipo: {type(e).__name__}")
        logger.error(f"Mensaje: {e}")
        logger.error("=" * 80, exc_info=True)
        raise FileNotFoundError(
            "No se encontraron credenciales de Google Drive. "
            "Prefect Secret Block 'google-credentials-valle-frio' no disponible. "
        "(2) Prefect Secret Block 'google-credentials' con el JSON, "
        "(3) GOOGLE_CREDENTIALS_B64 como variable de entorno con JSON en base64, "
        "(4) GOOGLE_CREDENTIALS_JSON como variable de entorno con JSON plano."
    )


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


def obtener_carpeta_comprobantes_proveedor(service, raiz_folder_id, nombre_proveedor, team_drive_id=None):
    """
    Obtiene o crea la estructura: Comprobantes Nóminas/[nombre_proveedor]

    Args:
        service: Google Drive service
        raiz_folder_id: ID de la carpeta raíz donde crear Comprobantes Nóminas
        nombre_proveedor: Nombre del proveedor para la subcarpeta
        team_drive_id: ID de Team Drive (si aplica)

    Returns:
        ID de la carpeta del proveedor
    """
    # Nivel 1: Crear o buscar "Comprobantes Nóminas"
    folder_comprobantes = obtener_o_crear_carpeta(
        service,
        "Comprobantes Nóminas",
        raiz_folder_id,
        team_drive_id
    )

    # Nivel 2: Crear o buscar carpeta del proveedor
    if not nombre_proveedor:
        nombre_proveedor = "Sin Proveedor"

    folder_proveedor = obtener_o_crear_carpeta(
        service,
        nombre_proveedor,
        folder_comprobantes,
        team_drive_id
    )

    logger.info(f"Carpeta de proveedor '{nombre_proveedor}' lista: {folder_proveedor}")
    return folder_proveedor


def copiar_archivo_drive(service, file_id, nombre_archivo, carpeta_destino_id):
    """
    Copia un archivo en Google Drive a una carpeta destino.

    Args:
        service: Google Drive service
        file_id: ID del archivo a copiar
        nombre_archivo: Nombre para la copia
        carpeta_destino_id: ID de la carpeta destino

    Returns:
        ID del archivo copiado, o None si falla
    """
    try:
        file_metadata = {
            "name": nombre_archivo,
            "parents": [carpeta_destino_id]
        }

        copied_file = service.files().copy(
            fileId=file_id,
            body=file_metadata,
            supportsAllDrives=True
        ).execute()

        logger.info(f"Archivo '{nombre_archivo}' copiado exitosamente a carpeta {carpeta_destino_id}")
        return copied_file.get("id")
    except Exception as e:
        logger.error(f"Error copiando archivo {file_id} a {carpeta_destino_id}: {e}")
        return None
