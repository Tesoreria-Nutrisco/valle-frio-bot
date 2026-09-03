"""
Descarga y limpia cartola cruda del banco desde Google Drive.
"""

import logging
import pandas as pd
from datetime import date, datetime, timedelta
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


def descargar_cartolas_rango(banco: str, dias_atras: int = 30, fecha_hasta: datetime = None) -> Optional[pd.DataFrame]:
    """
    Descargar y combinar TODAS las cartolas del banco en Drive navegando estructura:
    Cartolas > consorcio > 2026 > 08 > {03,17,18,...}

    Esto garantiza matching correcto contra egresos de múltiples días (no solo el más reciente).

    Args:
        banco: nombre del banco (ej: 'CONSORCIO')
        dias_atras: días de histórico a buscar hacia atrás (debe coincidir con obtener_egresos_softland)
        fecha_hasta: Fecha límite superior (default: datetime.now()).
                    En modo testing: usar la fecha simulada para buscar solo hacia atrás desde esa fecha.
                    En producción: usar None para que sea hoy.

    Returns:
        DataFrame combinado con cargos NÓMINA de todos los días, o None si no hay cartolas
    """
    if fecha_hasta is None:
        fecha_hasta = datetime.now()

    fecha_desde = (fecha_hasta - timedelta(days=dias_atras)).date()
    fecha_hasta_date = fecha_hasta.date() if isinstance(fecha_hasta, datetime) else fecha_hasta

    logger.info(f"Descargando TODAS las cartolas de {banco} en Drive ({fecha_desde} a {fecha_hasta_date})")

    drive = obtener_servicio_drive()

    try:
        # Navegar estructura: DRIVE_FOLDER_ID_CARTOLAS > consorcio > 2026 > 08
        cartolas_id = DRIVE_FOLDER_ID_CARTOLAS

        # Buscar consorcio
        query = f"parents='{cartolas_id}' and name='consorcio' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive.files().list(
            q=query,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=10,
            fields='files(id, name)'
        ).execute()
        consorcio_folders = results.get('files', [])
        if not consorcio_folders:
            logger.warning("No se encontró carpeta 'consorcio' dentro de Cartolas")
            return None

        consorcio_id = consorcio_folders[0]['id']

        # Meses que abarca el rango, en orden (puede cruzar de año)
        meses_del_rango = []
        cursor = fecha_desde.replace(day=1)
        ultimo_mes = fecha_hasta_date.replace(day=1)
        while cursor <= ultimo_mes:
            meses_del_rango.append((cursor.year, cursor.month))
            cursor = (cursor + timedelta(days=32)).replace(day=1)

        logger.info(f"Meses a revisar: {meses_del_rango}")

        # Descargar, limpiar y combinar TODAS las cartolas dentro del rango de fechas
        cartolas_limpias = []

        for anio_num, mes_num in meses_del_rango:
            mes_str = f"{mes_num:02d}"

            query = (f"parents='{consorcio_id}' and name='{anio_num}' "
                     f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
            year_folders = drive.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=10,
                fields='files(id, name)'
            ).execute().get('files', [])
            if not year_folders:
                logger.info(f"Sin carpeta de año {anio_num}, se omite")
                continue

            query = (f"parents='{year_folders[0]['id']}' and name='{mes_str}' "
                     f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
            month_folders = drive.files().list(
                q=query,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=10,
                fields='files(id, name)'
            ).execute().get('files', [])
            if not month_folders:
                logger.info(f"Sin carpeta de mes {anio_num}-{mes_str}, se omite")
                continue

            day_folders = drive.files().list(
                q=f"parents='{month_folders[0]['id']}' and trashed=false",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=100,
                orderBy='name',
                fields='files(id, name, mimeType)'
            ).execute().get('files', [])

            logger.info(f"{anio_num}-{mes_str}: {len(day_folders)} carpetas de día")

            for day_folder in day_folders:
                if 'folder' not in day_folder['mimeType']:
                    continue

                day_name = day_folder['name']

                # La fecha se arma con el año y mes DE LA CARPETA, no con los de
                # fecha_hasta: si no, un día de agosto se leería como de septiembre.
                try:
                    day_date = date(anio_num, mes_num, int(day_name))
                except ValueError:
                    logger.debug(f"  Saltando '{day_name}': no es un día válido")
                    continue

                if day_date < fecha_desde or day_date > fecha_hasta_date:
                    logger.debug(f"  Saltando {day_date}: fuera del rango")
                    continue

                query = f"parents='{day_folder['id']}' and name contains 'cartola' and trashed=false"
                day_files = drive.files().list(
                    q=query,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageSize=50,
                    fields='files(id, name, modifiedTime)'
                ).execute().get('files', [])

                for file_info in day_files:
                    file_name = file_info['name']
                    try:
                        logger.info(f"  Descargando {day_date}: {file_name}")

                        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                            request = drive.files().get_media(fileId=file_info['id'])
                            downloader = MediaIoBaseDownload(tmp, request)
                            done = False
                            while not done:
                                _, done = downloader.next_chunk()
                            tmp_path = tmp.name

                        df = _limpiar_cartola(tmp_path, banco)
                        if df is not None and len(df) > 0:
                            cartolas_limpias.append(df)
                            logger.info(f"    [OK] {len(df)} cargos NÓMINA encontrados")

                        Path(tmp_path).unlink()  # Eliminar temporal

                    except Exception as e:
                        logger.warning(f"  Error descargando {file_name}: {e}")
                        continue

        if not cartolas_limpias:
            logger.warning("No se pudo limpiar ninguna cartola")
            return None

        # Combinar todas en un DataFrame
        cartola_combinada = pd.concat(cartolas_limpias, ignore_index=True)

        # Cada archivo trae el mes acumulado hasta su fecha, así que un mismo cargo
        # aparece en varias cartolas. Sin deduplicar, el matcher procesaría el mismo
        # pago una vez por archivo.
        antes = len(cartola_combinada)
        clave = 'num' if 'num' in cartola_combinada.columns else None
        if clave:
            cartola_combinada = cartola_combinada.drop_duplicates(subset=[clave])
        else:
            cartola_combinada = cartola_combinada.drop_duplicates()

        if len(cartola_combinada) < antes:
            logger.info(f"Deduplicadas {antes - len(cartola_combinada)} líneas repetidas entre cartolas")

        logger.info(f"Cartola combinada: {len(cartola_combinada)} cargos NÓMINA totales")

        return cartola_combinada

    except Exception as e:
        logger.error(f"Error descargando cartolas de {banco}: {e}")
        raise


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
        # Buscar archivos cartola_*.xlsx globalmente (estructura de Drive: Bot-Cartolas/consorcio/YYYY/MM/DD/cartola_*.xlsx)
        query = (
            f"name contains 'cartola' "
            f"and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
            f"and modifiedTime > '{fecha_desde}' "
            f"and trashed=false"
        )

        results = drive.files().list(
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

        logger.info(f"[OK] Cartola descargada: {tmp_path}")

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

    # Buscar la fila de headers (típicamente contiene "Descripción", "Fecha", "Cargos", etc.)
    header_row_idx = None
    for idx, row in df_raw.iterrows():
        row_str = " ".join(row.dropna().astype(str).str.strip().str.upper())
        if "DESCRIPCIÓN" in row_str and "CARGOS" in row_str:
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
    for col in list(df_filtrado.columns):
        try:
            if df_filtrado[col].dtype == 'object':
                df_filtrado[col] = df_filtrado[col].astype(str).str.strip()
        except Exception as e:
            logger.debug(f"No se pudo hacer TRIM en columna {col}: {e}")

    # Normalizar nombres de columnas para matcher
    # La cartola real tiene: Num., Fecha Contable, Descripción, Cargos, Abonos, Saldo
    # Renombrar a: num, fecha, descripcion, monto
    rename_map = {}
    for col in df_filtrado.columns:
        if pd.isna(col):
            continue
        col_lower = str(col).lower()
        if 'fecha contable' in col_lower or 'fecha' in col_lower:
            rename_map[col] = 'fecha'
        elif 'cargos' in col_lower:
            rename_map[col] = 'monto'
        elif 'descripción' in col_lower or 'descripcion' in col_lower:
            rename_map[col] = 'descripcion'
        elif 'num.' in col_lower or 'num' in col_lower:
            rename_map[col] = 'num'

    # Eliminar columnas NaN
    df_filtrado = df_filtrado.dropna(axis=1, how='all')

    if rename_map:
        df_filtrado = df_filtrado.rename(columns=rename_map)
        logger.debug(f"Columnas renombradas: {rename_map}")

    logger.debug(f"Columnas finales: {list(df_filtrado.columns)}")
    return df_filtrado
