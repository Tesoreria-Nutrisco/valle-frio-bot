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
from config import DRIVE_FOLDER_ID_COMPROBANTES, BANCO_NOMBRE_CARPETA
from gaussdb_client import obtener_egresos_softland, obtener_contacto_productor
from cartola_cleaner import descargar_cartola_mas_reciente
from drive_utils import get_drive_service, get_carpeta_destino
from matcher import hacer_matching
from notificador import (
    enviar_notificacion_pago, enviar_alerta_desarrollador_no_cuadra,
    enviar_alerta_desarrollador_falta_contacto
)
from supabase_bot2 import (
    verificar_pago_ya_notificado, registrar_pago, actualizar_pago_a_notificado
)
import tempfile
from googleapiclient.http import MediaIoBaseDownload

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH / "bot2_run.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def buscar_comprobante_en_drive(monto: float, fecha_pago: str, productor_cod: str) -> Tuple[str, str]:
    """
    Busca y descarga comprobante de Drive.

    Estructura: /Comprobantes/{BANCO}/{YYYY}/{MM}/{DD}/comprobante_{banco}_{YYYYMMDD}_{RUT}.pdf

    Args:
        monto: monto del pago (no usado para búsqueda, solo para logging)
        fecha_pago: fecha en formato str (ej: "2026-08-10")
        productor_cod: RUT sin formato, solo dígitos (ej: "77460678")

    Returns:
        (ruta_local, ruta_drive) donde ambas son strings con la ruta del archivo
        (None, None) si no encuentra el comprobante
    """
    try:
        drive = get_drive_service()

        # Parsear fecha
        fecha_dt = datetime.strptime(str(fecha_pago), "%Y-%m-%d")
        yyyy = fecha_dt.strftime("%Y")
        mm = fecha_dt.strftime("%m")
        dd = fecha_dt.strftime("%d")
        yyyymmdd = fecha_dt.strftime("%Y%m%d")

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

        # Buscar archivo: comprobante_BANCO_YYYYMMDD_RUT.pdf
        archivo_esperado = f"comprobante_{BANCO_NOMBRE_CARPETA}_{yyyymmdd}_{productor_cod}.pdf"

        logger.debug(f"Buscando comprobante: {archivo_esperado} en carpeta {folder_id}")

        # Buscar en Drive
        query = (
            f"parents='{folder_id}' "
            f"and name='{archivo_esperado}' "
            f"and trashed=false"
        )

        results = drive.files().list(
            q=query,
            spaces="drive",
            pageSize=1,
            fields="files(id, name, webViewLink)"
        ).execute()

        files = results.get("files", [])

        if not files:
            logger.debug(f"No encontrado: {archivo_esperado}")
            return None, None

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

        # Retornar (ruta_local, ruta_drive)
        # ruta_drive es el webViewLink o el ID
        return tmp_path, web_link or f"https://drive.google.com/file/d/{file_id}"

    except Exception as e:
        logger.warning(f"Error buscando/descargando comprobante: {e}")
        return None, None


def procesar_confirmados(confirmados: List[Dict], fecha_pago: datetime) -> int:
    """
    Procesa egresos confirmados:
    1. Verificar que no fue notificado antes (evitar duplicados)
    2. Buscar comprobante en Drive
    3. Obtener contacto y decidir estado inicial
    4. Registrar en Supabase con estado apropiado ('confirmado' o 'pendiente_contacto')
    5. Si hay email: enviar y actualizar a 'notificado' si éxito
    6. Si no hay email: enviar alerta de falta contacto

    Estados:
    - 'confirmado': match confirmado, en proceso de notificar (tiene email)
    - 'pendiente_contacto': match confirmado pero sin email disponible
    - 'notificado': email enviado exitosamente

    Args:
        confirmados: Lista de egresos que cuadraron
        fecha_pago: Fecha de la cartola

    Returns:
        Cantidad de pagos procesados exitosamente (solo notificados)
    """
    procesados = 0

    for egreso in confirmados:
        cpb_ano = egreso.get('CpbAno', '')
        cpb_num = egreso.get('CpbNum', 'N/A')
        monto = egreso.get('monto_egreso', 0)
        productor_cod = egreso.get('productor_cod', 'N/A')

        try:
            logger.info(f"Procesando confirmado: Comprobante {cpb_num} | ${monto} | Productor {productor_cod}")

            # PASO 0: Verificar duplicado
            if verificar_pago_ya_notificado(cpb_ano, cpb_num, productor_cod):
                logger.info(f"  [SKIP] SALTADO: Ya fue notificado en corrida anterior")
                continue

            # PASO 1: Obtener contacto del productor (con fallback)
            email_productor, email_dte, email_contacto = obtener_contacto_productor(productor_cod)
            email_final = email_productor or email_dte or email_contacto

            # PASO 2: Buscar comprobante
            ruta_local, ruta_drive = buscar_comprobante_en_drive(
                monto, str(fecha_pago), productor_cod
            )
            logger.info(f"  Comprobante: {ruta_drive or 'no encontrado'}")

            # PASO 3: Decidir estado inicial según disponibilidad de email
            if email_final:
                # Caso A: Hay email — registrar como 'confirmado' e intentar envío
                registrar_pago(
                    cpb_ano=cpb_ano,
                    cpb_num=cpb_num,
                    monto=monto,
                    fecha_pago=fecha_pago,
                    productor_cod=productor_cod,
                    cuenta_banco=egreso.get('cuenta_banco', ''),
                    estado='confirmado',
                    intentos_match=egreso.get('intentos_match', 1),
                    comprobante_drive_path=ruta_drive
                )
                logger.info(f"  [OK] Registrado en Supabase (estado=confirmado)")

                # PASO 4A: Enviar email
                facturas = [{
                    'numero': cpb_num,
                    'fecha': str(fecha_pago),
                    'monto': monto
                }]
                email_enviado = enviar_notificacion_pago(
                    productor_email=email_final,
                    zonal_email=None,
                    monto_total=monto,
                    facturas=facturas,
                    comprobante_path=ruta_drive or "",
                    productor_nombre=productor_cod
                )

                # PASO 5A: Actualizar a 'notificado' SOLO si email se envió
                if email_enviado:
                    actualizar_pago_a_notificado(cpb_ano, cpb_num, productor_cod)
                    logger.info(f"  [OK] Email enviado y estado actualizado a notificado")
                    procesados += 1
                else:
                    logger.warning(f"  [FAIL] Email falló, manteniendo estado confirmado para reintentar próxima corrida")

            else:
                # Caso B: Sin email — registrar como 'pendiente_contacto'
                registrar_pago(
                    cpb_ano=cpb_ano,
                    cpb_num=cpb_num,
                    monto=monto,
                    fecha_pago=fecha_pago,
                    productor_cod=productor_cod,
                    cuenta_banco=egreso.get('cuenta_banco', ''),
                    estado='pendiente_contacto',
                    intentos_match=egreso.get('intentos_match', 1),
                    comprobante_drive_path=ruta_drive
                )
                logger.info(f"  [OK] Registrado en Supabase (estado=pendiente_contacto)")

                # PASO 4B: Enviar alerta de falta contacto
                enviar_alerta_desarrollador_falta_contacto(egreso)
                logger.info(f"  [OK] Alerta de falta contacto enviada")

        except Exception as e:
            logger.error(f"Error procesando confirmado {cpb_num}: {e}")
            continue

    logger.info(f"Confirmados procesados: {procesados}/{len(confirmados)}")
    return procesados


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
                fecha_pago=egreso.get('CpbFec'),
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

        egresos = obtener_egresos_softland(dias_atras=30)
        logger.info(f"[OK] Egresos obtenidos: {len(egresos)}")

        if not egresos:
            logger.info("No hay egresos para procesar")
            return

        # PASO 2: Descargar cartola
        logger.info("=" * 80)
        logger.info("PASO 2: Descargando cartola más reciente...")
        logger.info("=" * 80)

        cartola = descargar_cartola_mas_reciente(BANCO_CONSORCIO, dias_atras=30)
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

        # PASO 4: Procesar confirmados
        if confirmados:
            logger.info("=" * 80)
            logger.info("PASO 4: Procesando confirmados...")
            logger.info("=" * 80)
            procesados = procesar_confirmados(confirmados, fecha_hoy)
        else:
            procesados = 0

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
    fecha_testing = None
    if len(sys.argv) > 1:
        fecha_testing = sys.argv[1]

    main(fecha_testing)
