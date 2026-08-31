#!/usr/bin/env python3
"""
Bot 2: Reconciliación de Egresos Softland vs Cartola Bancaria
Flujo:
1. Obtener egresos de Softland (NB + productor)
2. Descargar cartola más reciente de Drive
3. Hacer matching (monto + fecha exacto, 3 reintentos con pausa)
4. Para confirmados: buscar comprobante -> registrar Supabase -> enviar email
5. Para no_cuadra: alertar desarrollador
6. Para sin_match: no hacer nada (aparecerá en próxima corrida)

Uso:
    python bot2/run.py [YYYY-MM-DD]  # Fecha de prueba (default: hoy)

Ejemplo:
    python bot2/run.py 2026-08-10    # Ejecutar contra 2026-08-10 (para testing)
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# Agregar bot1 y bot2 al path
bot1_path = str(Path(__file__).parent.parent / "bot1")
bot2_path = str(Path(__file__).parent)
sys.path.insert(0, bot1_path)
sys.path.insert(0, bot2_path)

from config import MODO_TEST, BANCO_CONSORCIO, CAPITAL_PROPIO, LOG_PATH, CORREO_PRUEBA
from config import DRIVE_FOLDER_ID_COMPROBANTES, DRIVE_FOLDER_ID_COMPROBANTES_NOMINAS, BANCO_NOMBRE_CARPETA
from gaussdb_client import obtener_egresos_softland, obtener_contacto_productor
from cartola_cleaner import descargar_cartolas_rango
from drive_utils import (
    get_drive_service, get_carpeta_destino,
    obtener_carpeta_comprobantes_proveedor, copiar_archivo_drive
)
from matcher import hacer_matching
from notificador import (
    enviar_notificacion_pago, enviar_alerta_desarrollador_no_cuadra,
    enviar_alerta_desarrollador_falta_contacto
)
from supabase_bot2 import (
    verificar_pago_ya_notificado, registrar_pago, actualizar_pago_a_notificado,
    marcar_nomina_procesada
)
import tempfile
from googleapiclient.http import MediaIoBaseDownload

# Configurar logging con UTF-8
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH / "bot2_run.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    encoding='utf-8'
)
logger = logging.getLogger(__name__)


def buscar_comprobante_en_drive(monto: float, fecha_pago: str, rut_productor: str) -> Tuple[str, str, str]:
    """
    Busca comprobante en Drive por RUT del productor.

    Estructura: /Comprobantes/{BANCO}/{YYYY}/{MM}/{DD}/comprobante_*_RUT.pdf

    Args:
        monto: monto del pago (no usado para búsqueda, solo para logging)
        fecha_pago: fecha en formato str (ej: "2026-08-10")
        rut_productor: RUT normalizado del productor (8 dígitos, ej: "76334187")

    Returns:
        (ruta_local, ruta_drive, nombre_archivo) donde:
        - ruta_local: path temporal del archivo descargado
        - ruta_drive: URL de Drive del archivo
        - nombre_archivo: nombre original del archivo en Drive (ej: "comprobante_consorcio_20260810_763341879.pdf")
        Returns (None, None, None) si no encuentra comprobante
    """
    try:
        drive = get_drive_service()

        # Parsear fecha (manejar datetime o string con timestamp)
        if isinstance(fecha_pago, datetime):
            fecha_dt = fecha_pago
        else:
            # Si es string, tomar solo la parte de fecha (antes del espacio)
            fecha_str = str(fecha_pago).split()[0]
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d")

        # Obtener carpeta destino en Drive
        TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
        try:
            folder_id = get_carpeta_destino(
                drive,
                DRIVE_FOLDER_ID_COMPROBANTES,
                BANCO_NOMBRE_CARPETA,
                fecha_dt,
                TEAM_DRIVE_ID
            )
        except Exception as e:
            logger.debug(f"No se pudo obtener carpeta de comprobantes: {e}")
            return None, None

        logger.info(f"Buscando comprobante para RUT {rut_productor} en carpeta {folder_id}")

        # Buscar archivo que contenga el RUT en el nombre
        # Formato esperado: comprobante_*.pdf con RUT al final
        query = (
            f"parents='{folder_id}' "
            f"and name contains 'comprobante_' "
            f"and name contains '{rut_productor}' "
            f"and mimeType='application/pdf' "
            f"and trashed=false"
        )

        logger.info(f"Query Drive: {query}")

        # Primero, listar TODOS los archivos en la carpeta (sin filtros) para diagnosticar
        logger.info(f"[DIAGNÓSTICO] Listando todos los archivos en carpeta {folder_id}")
        all_files_results = drive.files().list(
            q=f"parents='{folder_id}' and trashed=false",
            pageSize=100,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives"
        ).execute()
        all_files = all_files_results.get("files", [])
        logger.info(f"[DIAGNÓSTICO] Total de archivos en carpeta: {len(all_files)}")
        logger.info(f"[DIAGNÓSTICO] Nombres: {[f['name'] for f in all_files[:20]]}")

        # Ahora aplicar la búsqueda con filtros
        results = drive.files().list(
            q=query,
            pageSize=1,
            fields="files(id, name, webViewLink)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives"
        ).execute()

        files = results.get("files", [])
        logger.info(f"Resultados de búsqueda: {len(files)} archivo(s) encontrado(s)")
        if files:
            logger.info(f"  Archivos: {[f['name'] for f in files]}")

        if not files:
            logger.info(f"No se encontró comprobante para RUT {rut_productor}")
            return None, None, None

        file_id = files[0]['id']
        file_name = files[0]['name']
        web_link = files[0].get('webViewLink', '')

        logger.info(f"Comprobante encontrado: {file_name}")

        # Descargar localmente
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            request = drive.files().get_media(fileId=file_id)
            downloader = MediaIoBaseDownload(tmp, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            tmp_path = tmp.name

        logger.debug(f"Descargado localmente: {tmp_path}")

        # Retornar (ruta_local, ruta_drive, nombre_archivo_real)
        return tmp_path, web_link or f"https://drive.google.com/file/d/{file_id}", file_name

    except Exception as e:
        logger.warning(f"Error buscando/descargando comprobante para RUT {rut_productor}: {e}")
        return None, None, None


def procesar_confirmados(confirmados: List[Dict], fecha_pago: datetime) -> Tuple[int, set]:
    """
    Procesa egresos confirmados AGRUPADOS por (cpb_ano, cpb_num, productor_cod):
    1. Agrupa filas de Softland por comprobante+productor (en caso de múltiples facturas)
    2. Para cada grupo: suma montos y acumula facturas
    3. Verificar que no fue notificado antes (evitar duplicados)
    4. Buscar comprobante en Drive
    5. Obtener contacto y decidir estado inicial
    6. Registrar en Supabase con estado apropiado ('confirmado' o 'pendiente_contacto')
    7. Si hay email: enviar UN correo por grupo (con todas sus facturas) y actualizar a 'notificado' si éxito
    8. Si no hay email: enviar alerta de falta contacto

    Estados:
    - 'confirmado': match confirmado, en proceso de notificar (tiene email)
    - 'pendiente_contacto': match confirmado pero sin email disponible
    - 'notificado': email enviado exitosamente

    Args:
        confirmados: Lista de egresos que cuadraron (puede tener múltiples filas por productor)
        fecha_pago: Fecha de la cartola

    Returns:
        Tupla: (cantidad_procesados, set_de_ids_nominas_procesadas)
    """
    from collections import defaultdict

    procesados = 0
    nominas_procesadas = set()

    # PASO 0: Agrupar por (cpb_ano, cpb_num, productor_cod)
    # Esto maneja el caso donde un productor tiene múltiples facturas en el mismo comprobante
    grupos = defaultdict(list)
    for egreso in confirmados:
        clave = (egreso.get('CpbAno', ''), egreso.get('CpbNum', 'N/A'), egreso.get('productor_cod', 'N/A'))
        grupos[clave].append(egreso)

    logger.info(f"Confirmados agrupados: {len(grupos)} grupos únicos (comprobante+productor)")

    # PASO 1: Iterar sobre GRUPOS, no filas individuales
    for (cpb_ano, cpb_num, productor_cod), egresos_grupo in grupos.items():
        # Sumar montos individuales (monto_productor) del productor en este comprobante
        monto_total = sum(float(e.get('monto_productor', 0)) for e in egresos_grupo)

        # Acumular todas las facturas del grupo
        # Extraer número de factura real de la glosa (FT ó F1 + número)
        import re
        facturas = []
        for egreso in egresos_grupo:
            glosa = egreso.get('glosa', '')

            # Extraer número de factura: patrón "Pago: FT 9167; ..." o "Pago: F1 2267; ..."
            factura_numero = "N/A"
            if glosa:
                match = re.search(r'(FT|F1)\s*(\d+)', glosa)
                if match:
                    factura_numero = f"{match.group(1)} {match.group(2)}"

            facturas.append({
                'numero': factura_numero,  # "FT 9167" — número de factura real
                'fecha': str(fecha_pago),
                'fecha_pago': str(fecha_pago),
                'monto': float(egreso.get('monto_productor', 0))
            })

        try:
            logger.info(f"Procesando grupo: Comprobante {cpb_num} | Productor {productor_cod} | ${monto_total:,.0f} | {len(egresos_grupo)} factura(s)")

            # PASO 2: Verificar duplicado (una sola verificación por grupo)
            if verificar_pago_ya_notificado(cpb_ano, cpb_num, productor_cod):
                logger.info(f"  [SKIP] SALTADO: Ya fue notificado en corrida anterior")
                continue

            # PASO 3: Obtener contacto del productor (con fallback)
            email_productor, email_dte, email_contacto, productor_nombre = obtener_contacto_productor(productor_cod)
            email_final = email_productor or email_dte or email_contacto
            if not productor_nombre:
                productor_nombre = productor_cod  # Fallback al código si no hay nombre

            # PASO 4: Buscar comprobante por RUT completo (con DV, 9 dígitos)
            primer_egreso = egresos_grupo[0]
            # Obtener RUT completo del primer egreso (con DV)
            rut_completo = primer_egreso.get('productor_rut', '')
            if rut_completo:
                # Limpiar puntos y guión para obtener solo dígitos (9 dígitos con DV)
                rut_limpio = rut_completo.replace(".", "").replace("-", "").replace(" ", "")
            else:
                rut_limpio = productor_cod
            ruta_local, ruta_drive, nombre_archivo = buscar_comprobante_en_drive(
                monto_total, str(fecha_pago), rut_limpio
            )
            logger.info(f"  Comprobante: {ruta_drive or 'no encontrado'}")

            # PASO 5: Decidir estado inicial según disponibilidad de email
            if email_final:
                # Caso A: Hay email — registrar como 'confirmado' e intentar envío
                registrar_pago(
                    cpb_ano=cpb_ano,
                    cpb_num=cpb_num,
                    monto=monto_total,
                    fecha_pago=fecha_pago,
                    productor_cod=productor_cod,
                    cuenta_banco=primer_egreso.get('cuenta_banco', ''),
                    estado='confirmado',
                    intentos_match=primer_egreso.get('intentos_match', 1),
                    comprobante_drive_path=ruta_drive
                )
                logger.info(f"  [OK] Registrado en Supabase (estado=confirmado)")

                # PASO 6A: Enviar UN email por grupo (con TODAS sus facturas)
                email_enviado = enviar_notificacion_pago(
                    productor_email=email_final,
                    zonal_email=None,
                    monto_total=monto_total,
                    facturas=facturas,
                    comprobante_path=ruta_local or "",
                    nombre_archivo=nombre_archivo or "N/A",
                    productor_nombre=productor_nombre,
                    cpb_num=cpb_num
                )

                # PASO 7A: Actualizar a 'notificado' SOLO si email se envió
                if email_enviado:
                    actualizar_pago_a_notificado(cpb_ano, cpb_num, productor_cod)
                    logger.info(f"  [OK] Email enviado y estado actualizado a notificado")
                    procesados += 1

                    # PASO 7B: Copiar comprobante a Comprobantes Nóminas (solo si notificado)
                    if ruta_drive and nombre_archivo:
                        try:
                            drive = get_drive_service()
                            TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"

                            carpeta_proveedor = obtener_carpeta_comprobantes_proveedor(
                                drive,
                                DRIVE_FOLDER_ID_COMPROBANTES_NOMINAS,
                                productor_nombre,
                                TEAM_DRIVE_ID
                            )

                            query = (
                                f"name='{nombre_archivo}' "
                                f"and mimeType='application/pdf' "
                                f"and trashed=false"
                            )
                            results = drive.files().list(
                                q=query,
                                pageSize=1,
                                fields="files(id)",
                                supportsAllDrives=True,
                                includeItemsFromAllDrives=True,
                                corpora="allDrives"
                            ).execute()
                            files = results.get("files", [])

                            if files:
                                file_id = files[0]["id"]
                                copiar_archivo_drive(drive, file_id, nombre_archivo, carpeta_proveedor)
                                logger.info(f"  [OK] Comprobante copiado a Comprobantes Nóminas/{productor_nombre}/")
                        except Exception as e:
                            logger.warning(f"  Error copiando comprobante: {e}")
                else:
                    logger.warning(f"  [FAIL] Email falló, manteniendo estado confirmado para reintentar próxima corrida")

            else:
                # Caso B: Sin email — registrar como 'pendiente_contacto'
                registrar_pago(
                    cpb_ano=cpb_ano,
                    cpb_num=cpb_num,
                    monto=monto_total,
                    fecha_pago=fecha_pago,
                    productor_cod=productor_cod,
                    cuenta_banco=primer_egreso.get('cuenta_banco', ''),
                    estado='pendiente_contacto',
                    intentos_match=primer_egreso.get('intentos_match', 1),
                    comprobante_drive_path=ruta_drive
                )
                logger.info(f"  [OK] Registrado en Supabase (estado=pendiente_contacto)")

                # PASO 6B: Enviar alerta de falta contacto (una sola alerta por grupo)
                enviar_alerta_desarrollador_falta_contacto(primer_egreso)
                logger.info(f"  [OK] Alerta de falta contacto enviada")

        except Exception as e:
            logger.error(f"Error procesando grupo {cpb_num}/{productor_cod}: {e}")
            continue

        # Rastrear nóminas procesadas
        if 'id_nomina' in egresos_grupo[0]:
            nominas_procesadas.add(egresos_grupo[0]['id_nomina'])

    logger.info(f"Grupos procesados: {procesados}/{len(grupos)}")
    logger.info(f"Nóminas procesadas: {len(nominas_procesadas)}")
    return procesados, nominas_procesadas


def procesar_no_cuadra(no_cuadra: List[Dict]) -> int:
    """
    Procesa egresos que no cuadraron tras 3 reintentos.
    Registra en Supabase como 'discrepancia' y envía alerta al desarrollador.

    Args:
        no_cuadra: Lista de egresos sin match tras reintentos

    Returns:
        Cantidad de alertas enviadas
    """
    alertadas = 0

    for egreso in no_cuadra:
        cpb_ano = egreso.get('CpbAno', '')
        cpb_num = egreso.get('CpbNum', 'N/A')
        monto = egreso.get('monto_egreso', 0)
        intentos = egreso.get('intentos_match', 3)
        motivo = egreso.get('motivo', 'No encontrado en cartola')

        try:
            logger.warning(f"No cuadra: Comprobante {cpb_num} | ${monto} | {intentos} intentos")

            # Registrar en Supabase como 'rechazado' (no cuadró)
            registrar_pago(
                cpb_ano=cpb_ano,
                cpb_num=cpb_num,
                monto=monto,
                fecha_pago=egreso.get('fecha_carga'),
                productor_cod=egreso.get('productor_cod'),
                cuenta_banco=egreso.get('cuenta_banco', ''),
                estado='rechazado',
                intentos_match=intentos,
                comprobante_drive_path=None
            )

            # Enviar alerta
            enviar_alerta_desarrollador_no_cuadra(egreso, intentos)
            logger.info(f"  [OK] Alerta enviada al desarrollador")

            alertadas += 1

        except Exception as e:
            logger.error(f"Error procesando no_cuadra {cpb_num}: {e}")
            continue

    logger.info(f"No cuadra alertadas: {alertadas}/{len(no_cuadra)}")
    return alertadas


def sincronizar_comprobantes_historicos():
    """
    Sincroniza comprobantes de pagos ya notificados a la carpeta Comprobantes Nóminas.
    Útil para backfill de pagos históricos.
    """
    from supabase_bot2 import get_supabase

    logger.info("=" * 80)
    logger.info("SINCRONIZANDO COMPROBANTES HISTÓRICOS")
    logger.info("=" * 80)

    try:
        supabase = get_supabase()

        # Consultar pagos notificados
        response = supabase.table("pagos_bot2").select("*").eq("estado", "notificado").execute()
        pagos = response.data if response.data else []

        logger.info(f"Encontrados {len(pagos)} pagos notificados")

        drive = get_drive_service()
        TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
        copiados = 0

        for pago in pagos:
            try:
                # Obtener info del productor
                productor_cod = pago.get("productor_cod")
                email_final, _, _, productor_nombre = obtener_contacto_productor(productor_cod)

                if not productor_nombre:
                    productor_nombre = productor_cod

                # Buscar comprobante
                fecha_pago = pago.get("fecha_pago", "")
                rut_completo = pago.get("productor_rut", "")
                rut_limpio = rut_completo.replace(".", "").replace("-", "").replace(" ", "")

                ruta_local, ruta_drive, nombre_archivo = buscar_comprobante_en_drive(
                    float(pago.get("monto", 0)), str(fecha_pago), rut_limpio
                )

                if ruta_drive and nombre_archivo:
                    # Copiar a carpeta del proveedor
                    carpeta_proveedor = obtener_carpeta_comprobantes_proveedor(
                        drive,
                        DRIVE_FOLDER_ID_COMPROBANTES_NOMINAS,
                        productor_nombre,
                        TEAM_DRIVE_ID
                    )

                    query = (
                        f"name='{nombre_archivo}' "
                        f"and mimeType='application/pdf' "
                        f"and trashed=false"
                    )
                    results = drive.files().list(
                        q=query,
                        pageSize=1,
                        fields="files(id)",
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                        corpora="allDrives"
                    ).execute()
                    files = results.get("files", [])

                    if files:
                        file_id = files[0]["id"]
                        copiar_archivo_drive(drive, file_id, nombre_archivo, carpeta_proveedor)
                        copiados += 1
                        logger.info(f"  [OK] {productor_nombre}: {nombre_archivo}")
            except Exception as e:
                logger.warning(f"  Error con {pago.get('productor_cod')}: {e}")
                continue

        logger.info("=" * 80)
        logger.info(f"Comprobantes sincronizados: {copiados}/{len(pagos)}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error sincronizando históricos: {e}")
        import traceback
        logger.error(traceback.format_exc())


def main(fecha_testing: str = None):
    """
    Orquestación principal de Bot 2.

    Args:
        fecha_testing: Fecha para testing (formato YYYY-MM-DD). Default: hoy
    """
    logger.info("=" * 80)
    logger.info("INICIANDO BOT 2 - RECONCILIACIÓN EGRESOS")
    logger.info("=" * 80)

    # Determinar fecha
    if fecha_testing:
        try:
            fecha_hoy = datetime.strptime(fecha_testing, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Formato de fecha inválido: {fecha_testing}. Usar YYYY-MM-DD")
            sys.exit(1)
    else:
        fecha_hoy = datetime.now()

    logger.info(f"Fecha: {fecha_hoy.strftime('%Y-%m-%d')}")
    logger.info(f"Modo: {'TEST' if MODO_TEST else 'PRODUCCIÓN'}")
    if MODO_TEST:
        logger.info(f"  Correos enviados a: {CORREO_PRUEBA}")

    try:
        # PASO 1: Obtener egresos de Softland
        logger.info("=" * 80)
        logger.info("PASO 1: Consultando Softland (últimos 30 días)...")
        logger.info("=" * 80)

        egresos = obtener_egresos_softland(dias_atras=30, fecha_hasta=fecha_hoy)
        logger.info(f"[OK] Egresos obtenidos: {len(egresos)}")

        if not egresos:
            logger.info("No hay egresos para procesar")
            return

        # PASO 2: Descargar cartolas del rango completo (30 días)
        logger.info("=" * 80)
        logger.info("PASO 2: Descargando cartolas (últimos 30 días)...")
        logger.info("=" * 80)

        cartola = descargar_cartolas_rango(BANCO_CONSORCIO, dias_atras=30, fecha_hasta=fecha_hoy)
        if cartola is None or cartola.empty:
            logger.warning("No se encontró cartola. Abortando.")
            return

        logger.info(f"[OK] Cartola descargada: {len(cartola)} cargos NÓMINA")

        # PASO 3: Hacer matching
        logger.info("=" * 80)
        logger.info("PASO 3: Matching (monto + fecha exacto, 3 reintentos)...")
        logger.info("=" * 80)

        resultado_matching = hacer_matching(
            egresos,
            cartola,
            banco=BANCO_CONSORCIO
        )

        confirmados = resultado_matching['confirmados']
        sin_match = resultado_matching['sin_match']
        no_cuadra = resultado_matching['no_cuadra']

        logger.info(f"Resultado matching:")
        logger.info(f"  [OK] Confirmados: {len(confirmados)}")
        logger.info(f"  [PAUSE] Sin match: {len(sin_match)}")
        logger.info(f"  [FAIL] No cuadra: {len(no_cuadra)}")

        # Detalles de confirmados
        if confirmados:
            logger.info("")
            logger.info("DETALLE CONFIRMADOS:")
            for idx, egreso in enumerate(confirmados, 1):
                logger.info(f"  {idx}. CpbNum: {egreso.get('CpbNum', 'N/A')} | "
                          f"Productor: {egreso.get('productor_cod', 'N/A')} | "
                          f"Monto: ${egreso.get('monto_egreso', 0):,.0f} | "
                          f"Fecha: {egreso.get('fecha_carga', 'N/A')}")

        # Detalles de no_cuadra
        if no_cuadra:
            logger.info("")
            logger.info("DETALLE NO CUADRA:")
            for idx, egreso in enumerate(no_cuadra, 1):
                motivo = egreso.get('motivo', 'monto no coincide')
                logger.info(f"  {idx}. CpbNum: {egreso.get('CpbNum', 'N/A')} | "
                          f"Productor: {egreso.get('productor_cod', 'N/A')} | "
                          f"Monto: ${egreso.get('monto_egreso', 0):,.0f} | "
                          f"Fecha: {egreso.get('fecha_carga', 'N/A')} | "
                          f"Motivo: {motivo}")

        # PASO 4: Procesar confirmados
        nominas_procesadas = set()
        if confirmados:
            logger.info("=" * 80)
            logger.info("PASO 4: Procesando confirmados...")
            logger.info("=" * 80)
            procesados, nominas_procesadas = procesar_confirmados(confirmados, fecha_hoy)
        else:
            procesados = 0

        # PASO 4B: Marcar nóminas como 'procesado' en Supabase
        if nominas_procesadas:
            logger.info("=" * 80)
            logger.info(f"PASO 4B: Marcando {len(nominas_procesadas)} nóminas como procesadas...")
            logger.info("=" * 80)
            for id_nomina in nominas_procesadas:
                if marcar_nomina_procesada(id_nomina):
                    logger.info(f"  [OK] Nómina {id_nomina} marcada como procesada")
                else:
                    logger.warning(f"  [FAIL] No se pudo marcar nómina {id_nomina}")

        # PASO 5: Procesar no cuadra
        if no_cuadra:
            logger.info("=" * 80)
            logger.info("PASO 5: Procesando no cuadra (alertas)...")
            logger.info("=" * 80)
            alertadas = procesar_no_cuadra(no_cuadra)
        else:
            alertadas = 0

        # Resumen
        logger.info("=" * 80)
        logger.info("RESUMEN BOT 2")
        logger.info("=" * 80)
        logger.info(f"Egresos consultados:  {len(egresos)}")
        logger.info(f"Confirmados:          {len(confirmados)} procesados")
        logger.info(f"Sin match:            {len(sin_match)} (próxima corrida)")
        logger.info(f"No cuadra:            {len(no_cuadra)} alertas enviadas")
        logger.info(f"Pagos notificados:    {procesados}")
        logger.info("=" * 80)
        logger.info("BOT 2 COMPLETADO EXITOSAMENTE")
        logger.info("=" * 80)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"BOT 2 FALLÓ: {e}")
        logger.error("=" * 80)
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":
        # Sincronizar comprobantes históricos
        sincronizar_comprobantes_historicos()
    else:
        fecha_testing = None
        if len(sys.argv) > 1:
            fecha_testing = sys.argv[1]

        main(fecha_testing)
