"""
Descarga y limpia cartola cruda del banco desde Google Drive.
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import tempfile

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from config import (
    GOOGLE_DRIVE_CREDENTIALS_PATH,
    DRIVE_FOLDER_ID_CARTOLAS,
    TEAM_DRIVE_ID
)

logger = logging.getLogger(__name__)


def obtener_servicio_drive():
    """Inicializa cliente de Google Drive."""
    scopes = ["https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_file(
        GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes
    )
    return build("drive", "v3", credentials=credentials)


def descargar_cartola_mas_reciente(banco: str, dias_atras: int = 5) -> Optional[pd.DataFrame]:
    """
    Busca y descarga la cartola más reciente del banco en Drive.

    Args:
        banco: nombre del banco (ej: 'CONSORCIO')
        dias_atras: días de histórico a buscar

    Returns:
        DataFrame limpio con cargos NÓMINA, o None si no hay cartola
    """
    logger.info(f"Buscando cartola más reciente de {banco} en Drive (últimos {dias_atras} días)")

    drive = obtener_servicio_drive()
    fecha_desde = (datetime.now() - timedelta(days=dias_atras)).strftime("%Y-%m-%d")

    try:
        # Buscar archivos cartola_YYYYMMDD.xlsx en DRIVE_FOLDER_ID_CARTOLAS
        query = (
            f"parents='{DRIVE_FOLDER_ID_CARTOLAS}' "
            f"and name contains 'cartola' "
            f"and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
            f"and createdTime > '{fecha_desde}' "
            f"and trashed=false"
        )

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
        if not files:
            logger.warning(f"No se encontró cartola de {banco} en los últimos {dias_atras} días")
            return None

        logger.info(f"Cartola más reciente: {files[0]['name']}")

        # Descargar el más reciente
        file_id = files[0]['id']
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            request = drive.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            tmp_path = tmp.name

        logger.info(f"✓ Cartola descargada: {tmp_path}")

        # Limpiar y filtrar
        df = _limpiar_cartola(tmp_path, banco)
        Path(tmp_path).unlink()  # Eliminar temporal

        return df

    except Exception as e:
        logger.error(f"Error descargando cartola de {banco}: {e}")
        raise


def _limpiar_cartola(ruta_archivo: str, banco: str) -> pd.DataFrame:
    """
    Limpia cartola cruda: quita encabezado/logo, filtra solo "CARGO NÓMINA".

    Args:
        ruta_archivo: ruta al Excel descargado
        banco: nombre del banco

    Returns:
        DataFrame limpio
    """
    logger.info(f"Limpiando cartola de {banco}")

    # Leer Excel (saltando filas del encabezado si es necesario)
    # Buscar la fila con "Descripción" como header real
    df_raw = pd.read_excel(ruta_archivo, sheet_name=0, header=None)

    # Buscar la fila de headers (típicamente contiene "Descripción", "Fecha", "Monto", etc.)
    header_row_idx = None
    for idx, row in df_raw.iterrows():
        row_str = " ".join(row.dropna().astype(str).str.strip().str.upper())
        if "DESCRIPCIÓN" in row_str and "MONTO" in row_str:
            header_row_idx = idx
            break

    if header_row_idx is None:
        logger.warning("No se encontró fila de headers en cartola, usando índice 0")
        header_row_idx = 0

    # Usar esa fila como headers
    df = pd.DataFrame(df_raw.iloc[header_row_idx + 1:].values, columns=df_raw.iloc[header_row_idx].values)
    df = df.dropna(how='all')  # Eliminar filas vacías

    # Normalizar nombres de columnas
    df.columns = df.columns.str.strip().str.lower()

    logger.info(f"Cartola bruta: {len(df)} filas")

    # Filtrar solo "CARGO NÓMINA"
    if 'descripción' in df.columns:
        df_filtrado = df[df['descripción'].astype(str).str.contains('CARGO NÓMINA', case=False, na=False)]
    elif 'descripcion' in df.columns:
        df_filtrado = df[df['descripcion'].astype(str).str.contains('CARGO NÓMINA', case=False, na=False)]
    else:
        logger.warning("No se encontró columna 'descripción' en cartola")
        df_filtrado = df

    logger.info(f"Cartola filtrada (CARGO NÓMINA): {len(df_filtrado)} filas")

    # TRIM de campos texto
    for col in df_filtrado.columns:
        if df_filtrado[col].dtype == 'object':
            df_filtrado[col] = df_filtrado[col].astype(str).str.strip()

    return df_filtrado
