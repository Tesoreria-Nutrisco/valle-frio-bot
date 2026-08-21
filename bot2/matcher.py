"""
Matching entre cartola bancaria y egresos de Softland (Opción D).

OPCIÓN D: Itera cartola → extrae id_nomina de glosa → valida → compara.
NO usa monto como criterio de búsqueda.

Flujo por CADA LÍNEA de cartola:
1. Extraer id_nomina de SU glosa ("PROVEEDORES ID (\d+)")
2. Validar id_nomina en Supabase bot1_nominas_descargadas (estado='completo')
3. Descargar nómina Excel desde Drive
4. Extraer beneficiarios (RUT, monto) de esa nómina
5. Agrupar egresos Softland por (cpb_ano, cpb_num, productor_cod)
6. Comparar: ¿monto de cargo = suma beneficiarios? ¿RUTs + montos coinciden exacto?
7. Si TODO coincide: CONFIRMADO | Si no: NO_CUADRA
"""

import logging
import re
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from pathlib import Path
from datetime import datetime
import pandas as pd
import tempfile

from config import BANCO_CUENTA_MAP
from supabase_bot2 import obtener_nominas_descargadas_supabase
from nomina_parser import extraer_beneficiarios_nomina, normalizar_rut
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)


def _obtener_id_nomina_de_glosa(glosa: str) -> Optional[str]:
    """
    Extrae id_nomina de la glosa usando regex "PROVEEDORES ID (\d+)".

    Args:
        glosa: texto de glosa de cartola

    Returns:
        id_nomina como string si se encuentra, None si no
    """
    if not glosa:
        return None

    match = re.search(r'PROVEEDORES ID (\d+)', str(glosa), re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _descargar_nomina_excel_desde_drive(
    id_nomina: str
) -> Optional[str]:
    """
    Descarga nómina Excel desde Drive (si existe).

    Args:
        id_nomina: ID de nómina (ej: "1965890")

    Returns:
        Ruta local al archivo descargado, None si no existe
    """
    try:
        # Inicializar Drive API
        cred_path = Path(__file__).parent.parent / "credentials.json"
        if not cred_path.exists():
            logger.warning(f"Credenciales de Drive no encontradas")
            return None

        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_file(str(cred_path), scopes=scopes)
        drive = build("drive", "v3", credentials=credentials)

        # Buscar archivo con el ID de nómina en el nombre
        query = f"name contains '{id_nomina}' and name contains '.xlsx' and trashed=false"
        results = drive.files().list(
            q=query,
            spaces="drive",
            pageSize=10,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        archivos = results.get("files", [])
        if not archivos:
            logger.debug(f"No se encontró nómina Excel para ID {id_nomina} en Drive")
            return None

        # Tomar el primer archivo encontrado
        archivo_id = archivos[0]["id"]
        archivo_nombre = archivos[0]["name"]

        # Descargar a archivo temporal
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            request = drive.files().get_media(fileId=archivo_id)
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            tmp_path = tmp.name

        logger.debug(f"Descargada nómina Excel {id_nomina} desde Drive: {archivo_nombre}")
        return tmp_path

    except Exception as e:
        logger.warning(f"Error descargando nómina Excel para ID {id_nomina}: {e}")
        return None


def _agrupar_egresos_por_productor(
    egresos_softland: List[Dict]
) -> Dict[Tuple, Dict]:
    """
    Agrupa egresos por (cpb_ano, cpb_num, productor_cod).

    Args:
        egresos_softland: lista de egresos

    Returns:
        Dict con key=(cpb_ano, cpb_num, productor_cod) y value={
            'monto_total': suma de monto_productor,
            'egresos': lista de egresos del grupo,
            'productor_cod': código productor,
            'cpb_ano': año comprobante,
            'cpb_num': número comprobante
        }
    """
    grupos = defaultdict(lambda: {
        'monto_total': 0.0,
        'egresos': [],
        'productor_cod': None,
        'cpb_ano': None,
        'cpb_num': None
    })

    for egreso in egresos_softland:
        key = (egreso['CpbAno'], egreso['CpbNum'], egreso['productor_cod'])

        grupos[key]['monto_total'] += egreso['monto_productor']
        grupos[key]['egresos'].append(egreso)
        grupos[key]['productor_cod'] = egreso['productor_cod']
        grupos[key]['cpb_ano'] = egreso['CpbAno']
        grupos[key]['cpb_num'] = egreso['CpbNum']

    return grupos


def hacer_matching(
    egresos_softland: List[Dict],
    cartola_limpia: pd.DataFrame,
    banco: str,
    max_intentos: int = 3  # No se usa en Opción D, pero se mantiene para compatibilidad
) -> Dict[str, list]:
    """
    Cruza egresos de Softland contra cartola usando OPCIÓN D (cartola → id_nomina).

    FLUJO (por cada línea de cartola):
    1. Extraer id_nomina de glosa de esa línea ("PROVEEDORES ID (\d+)")
    2. Validar id_nomina en Supabase bot1_nominas_descargadas (estado='completo')
    3. Descargar nómina Excel de ESA nómina específica
    4. Extraer beneficiarios (RUT, monto) de esa nómina
    5. Agrupar egresos Softland por (cpb_ano, cpb_num, productor_cod)
    6. Para CADA grupo de egresos:
       a. ¿Existe un cargo en cartola que pertenezca a ESTA nómina con monto exacto?
       b. ¿Los beneficiarios de la nómina coinciden exacto con los egresos de Softland?
    7. Si TODO coincide: CONFIRMADO | Si no: NO_CUADRA

    Args:
        egresos_softland: lista de egresos de Softland
        cartola_limpia: DataFrame con cargos de cartola
        banco: nombre del banco
        max_intentos: parámetro legacy (no se usa)

    Returns:
        Dict con:
        {
            'confirmados': [egresos que cuadraron],
            'sin_match': [egresos NO encontrados en cartola],
            'no_cuadra': [egresos con discrepancia]
        }
    """
    logger.info(f"[OPCIÓN D] Iniciando matching: {len(egresos_softland)} egresos vs {len(cartola_limpia)} cargos")
    logger.debug(f"Columnas cartola: {list(cartola_limpia.columns)}")

    cuentas_busqueda = BANCO_CUENTA_MAP.get(banco, [banco])
    logger.info(f"Banco: {banco} | Cuentas a buscar: {cuentas_busqueda}")

    confirmados = []
    sin_match = []
    no_cuadra = []

    # Agrupar egresos Softland por productor (para comparación posterior)
    grupos_softland = _agrupar_egresos_por_productor(egresos_softland)
    logger.info(f"Egresos agrupados en {len(grupos_softland)} grupos por productor")

    # Caché de nóminas validadas para no repetir llamadas
    nominas_validas = {}
    nominas_descargadas = obtener_nominas_descargadas_supabase()

    # PASO: Marcar automáticamente nóminas anuladas como bot2_estado='anulado'
    # (para evitar que se reintenten en cada corrida)
    for nomina in nominas_descargadas:
        if nomina.get('estado') == 'anulada' and nomina.get('bot2_estado') != 'anulado':
            id_nomina = nomina.get('id_nomina')
            logger.info(f"[AUTO-MARCAR] Nómina {id_nomina} tiene estado='anulada', marcando bot2_estado='anulado'...")
            try:
                from supabase_bot2 import marcar_nomina_anulada
                if marcar_nomina_anulada(id_nomina):
                    logger.info(f"  [OK] Nómina {id_nomina} marcada como anulada")
            except Exception as e:
                logger.warning(f"  [WARN] No se pudo marcar nómina {id_nomina} como anulada: {e}")

    # Filtrar solo nóminas con bot2_estado='pendiente' (evita reprocesar nóminas procesadas o anuladas)
    ids_nominas_validas = {n.get('id_nomina'): n for n in nominas_descargadas
                           if n.get('bot2_estado') == 'pendiente'}

    logger.info(f"Nóminas a procesar (bot2_estado='pendiente'): {len(ids_nominas_validas)} de {len(nominas_descargadas)}")

    # ITERAR CARTOLA: línea por línea
    logger.info(f"Iterando {len(cartola_limpia)} líneas de cartola...")

    for idx, cargo_row in cartola_limpia.iterrows():
        cargo_monto = cargo_row.get('monto')
        # Cartola real usa 'descripcion', no 'glosa'
        cargo_glosa = cargo_row.get('descripcion', '') or cargo_row.get('glosa', '')
        cargo_fecha = cargo_row.get('fecha')

        logger.debug(f"Línea cartola #{idx}: ${cargo_monto} | Glosa: {cargo_glosa[:50]}...")

        # PASO 1: Extraer ID de nómina de ESTA línea de cartola
        id_nomina = _obtener_id_nomina_de_glosa(cargo_glosa)

        if not id_nomina:
            logger.debug(f"  [SKIP] Línea cartola sin ID de nómina en glosa")
            continue

        logger.debug(f"  [1/6] ID de nómina extraído: {id_nomina}")

        # PASO 2: Validar ID de nómina en Supabase
        if id_nomina not in ids_nominas_validas:
            logger.debug(f"  [SKIP] Nómina {id_nomina} no registrada en Supabase")
            continue

        logger.debug(f"  [2/6] Nómina {id_nomina} validada en Supabase")

        # PASO 3: Descargar nómina Excel de ESTA nómina
        if id_nomina not in nominas_validas:
            logger.debug(f"  [3/6] Descargando nómina {id_nomina} desde Drive...")
            nomina_excel_path = _descargar_nomina_excel_desde_drive(id_nomina)

            if not nomina_excel_path:
                logger.warning(f"  [SKIP] No se pudo descargar nómina {id_nomina}")
                continue

            nominas_validas[id_nomina] = nomina_excel_path
        else:
            nomina_excel_path = nominas_validas[id_nomina]
            logger.debug(f"  [3/6] Nómina {id_nomina} ya está en caché")

        # PASO 4: Extraer beneficiarios de ESTA nómina
        logger.debug(f"  [4/6] Extrayendo beneficiarios de nómina {id_nomina}...")
        try:
            beneficiarios = extraer_beneficiarios_nomina(nomina_excel_path)
            beneficiarios_dict = {rut: monto for rut, monto in beneficiarios}
            logger.debug(f"  [4/6] Beneficiarios extraídos: {len(beneficiarios)}")
        except Exception as e:
            logger.warning(f"  [SKIP] Error extrayendo beneficiarios de nómina {id_nomina}: {e}")
            continue

        # PASO 5: Calcular suma total de beneficiarios
        monto_total_beneficiarios = sum(m for _, m in beneficiarios)
        logger.debug(f"  [5/6] Monto total de beneficiarios: ${monto_total_beneficiarios}")

        # PASO 6: Comparar con cargo de cartola
        logger.debug(f"  [6/6] Comparando: cargo cartola ${cargo_monto} vs beneficiarios ${monto_total_beneficiarios}")

        # Tolerancia 0.01 por redondeo
        if abs(float(cargo_monto) - monto_total_beneficiarios) > 0.01:
            logger.debug(f"  [SKIP] Montos no coinciden (cargo=${cargo_monto}, beneficiarios=${monto_total_beneficiarios})")
            continue

        logger.debug(f"  [OK] Monto de cargo coincide exacto con suma de beneficiarios")

        # PASO 7: Buscar qué egresos Softland corresponden a ESTA nómina
        # Criterio: buscar egresos cuyo productor_cod esté en los beneficiarios de esta nómina
        # y el monto sea exacto

        egresos_coincidencia = []

        for (cpb_ano, cpb_num, productor_cod), grupo_info in grupos_softland.items():
            monto_grupo = grupo_info['monto_total']
            egresos_grupo = grupo_info['egresos']

            # Normalizar productor_cod para comparar contra beneficiarios normalizados
            productor_rut_normalizado = normalizar_rut(productor_cod)
            logger.debug(f"    Productor {productor_cod} → normalizado: {productor_rut_normalizado}")

            # ¿El productor_cod (normalizado) está en los beneficiarios?
            if productor_rut_normalizado not in beneficiarios_dict:
                logger.debug(f"    {productor_rut_normalizado} NO encontrado en beneficiarios de nómina {id_nomina}")
                continue

            # ¿El monto del grupo coincide exacto con el beneficiario?
            monto_beneficiario = beneficiarios_dict[productor_rut_normalizado]
            if abs(monto_grupo - monto_beneficiario) > 0.01:
                logger.debug(f"    Productor {productor_rut_normalizado}: monto ${monto_grupo} ≠ nómina ${monto_beneficiario}")
                continue

            logger.info(f"  [OK] CONFIRMADO: {cpb_num} | Productor {productor_rut_normalizado} | Nómina {id_nomina}")

            # Registrar como confirmados
            for egreso in egresos_grupo:
                confirmados.append({
                    **egreso,
                    'cargo_cartola': cargo_row.to_dict(),
                    'id_nomina': id_nomina,
                    'monto_beneficiario': monto_beneficiario,
                    'intentos_match': 1
                })

            egresos_coincidencia.append((cpb_ano, cpb_num, productor_cod))

        # Marcar estos egresos como procesados para no procesarlos nuevamente
        for key in egresos_coincidencia:
            del grupos_softland[key]

    # PASO FINAL: Procesar egresos no coincidentes
    # Los que quedaron en grupos_softland no encontraron línea de cartola con su nómina

    logger.info(f"Procesando {len(grupos_softland)} grupos de egresos sin coincidencia en cartola...")

    for (cpb_ano, cpb_num, productor_cod), grupo_info in grupos_softland.items():
        egresos_grupo = grupo_info['egresos']

        # Buscar si existe ALGÚN cargo en cartola con monto similar (pero sin id_nomina válido)
        # para distinguir "cartola aún no tiene el cargo" vs "cartola tiene algo pero discrepancia"

        egreso_base = egresos_grupo[0]
        monto_busqueda = grupo_info['monto_total']
        cuenta_egreso = egreso_base.get('cuenta_banco', '')

        # Validar cuenta
        if cuenta_egreso and cuenta_egreso not in cuentas_busqueda:
            logger.warning(f"[SKIP] {cpb_num}: cuenta {cuenta_egreso} no válida para {banco}")
            for egreso in egresos_grupo:
                sin_match.append({
                    **egreso,
                    'motivo': f'Cuenta {cuenta_egreso} no válida para banco {banco}'
                })
            continue

        # Buscar si existe algún cargo con ese monto (sin validación de nómina)
        cargos_monto_similar = cartola_limpia[
            (cartola_limpia['monto'].astype(float) - monto_busqueda).abs() < 0.01
        ]

        if len(cargos_monto_similar) > 0:
            # Existe cargo pero no coincidió con nómina válida → NO_CUADRA
            logger.warning(f"[FAIL] {cpb_num}: existe cargo por ${monto_busqueda} pero no coincide con nómina válida")
            for egreso in egresos_grupo:
                no_cuadra.append({
                    **egreso,
                    'intentos_match': 1,
                    'motivo': f'Cargo existe (${monto_busqueda}) pero no coincide con nómina válida (falta ID, nómina no registrada, beneficiarios no coinciden)'
                })
        else:
            # No existe cargo con ese monto en cartola → SIN_MATCH
            logger.info(f"[PAUSE] {cpb_num}: monto ${monto_busqueda} no existe aún en cartola")
            for egreso in egresos_grupo:
                sin_match.append({
                    **egreso,
                    'motivo': f'Monto ${monto_busqueda} no encontrado en cartola'
                })

    logger.info(f"Resultado matching [Opción D]:")
    logger.info(f"  [OK] Confirmados: {len(confirmados)}")
    logger.info(f"  [PAUSE] Sin match: {len(sin_match)}")
    logger.info(f"  [FAIL] No cuadra: {len(no_cuadra)}")

    return {
        'confirmados': confirmados,
        'sin_match': sin_match,
        'no_cuadra': no_cuadra
    }
