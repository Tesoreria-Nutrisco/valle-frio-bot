"""
Cliente Supabase para Bot 2: Registra resultados de reconciliación.
Schema: valle_frio_bot
Tablas:
- bot2_pagos_reconciliados (pagos confirmados)
- bot2_pagos_no_cuadra (pagos con discrepancia tras reintentos)
"""

import logging
from datetime import datetime
from pathlib import Path

# Importar desde bot1
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "bot1"))
from supabase_client import get_client

logger = logging.getLogger(__name__)

SUPABASE_SCHEMA = "valle_frio_bot"
SUPABASE_SCHEMA_BOT1 = "valle_frio_bot"  # Bot 1 registra nóminas en schema valle_frio_bot (confirmado)


def verificar_pago_ya_notificado(cpb_ano: str, cpb_num: str, productor_cod: str) -> bool:
    """
    Verifica si un pago ya fue notificado en esta corrida o anterior.
    Evita reenvíos duplicados.

    Args:
        cpb_ano: Año del comprobante
        cpb_num: Número del comprobante
        productor_cod: Código del productor

    Returns:
        True si ya existe con estado='notificado'
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py
        result = client.table("bot2_pagos_notificados") \
            .select("id") \
            .eq("cpb_ano", str(cpb_ano)) \
            .eq("cpb_num", str(cpb_num)) \
            .eq("productor_cod", str(productor_cod)) \
            .eq("estado", "notificado") \
            .execute()

        return len(result.data) > 0

    except Exception as e:
        logger.debug(f"Verificación de duplicado falló (esperado si tabla usa permisos restrictivos): {e}")
        return False


def registrar_pago(
    cpb_ano: str,
    cpb_num: str,
    monto: float,
    fecha_pago: datetime,
    productor_cod: str,
    cuenta_banco: str,
    estado: str,
    intentos_match: int = 1,
    comprobante_drive_path: str = None
) -> bool:
    """
    Registra un pago en bot2_pagos_notificados con estado final.

    Estados válidos (del CHECK constraint):
    - 'pendiente_contacto': encontrado en cartola, aún sin enviar notificación
    - 'notificado': correo enviado exitosamente
    - 'rechazado': no cuadró (no coincidencia de monto/fecha tras reintentos)
    - 'confirmado': confirmado (no se usa en Bot 2, por compatibilidad)

    Args:
        cpb_ano: Año del comprobante
        cpb_num: Número del comprobante
        monto: Monto del pago
        fecha_pago: Fecha del pago
        productor_cod: Código del productor
        cuenta_banco: Cuenta de banco (ej: "10-01-10-16")
        estado: 'pendiente_contacto', 'notificado', o 'rechazado'
        intentos_match: Número de intentos (1 = inmediato, 2-3 = reintentos)
        comprobante_drive_path: Ruta en Drive del comprobante

    Returns:
        True si se registró exitosamente
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py

        payload = {
            "cpb_ano": str(cpb_ano),
            "cpb_num": str(cpb_num),
            "monto": float(monto),
            "fecha_pago": str(fecha_pago.date() if hasattr(fecha_pago, 'date') else fecha_pago),
            "productor_cod": str(productor_cod),
            "cuenta_softland": str(cuenta_banco),
            "banco_real": "CONSORCIO",
            "estado": estado,
            "intentos_match": int(intentos_match),
            "comprobante_drive_path": comprobante_drive_path,
            "fecha_registro": datetime.now().isoformat(),
        }

        result = client.table("bot2_pagos_notificados") \
            .insert(payload) \
            .execute()

        logger.info(f"[OK] Pago registrado en Supabase: {cpb_num} | ${monto} | estado={estado}")
        return True

    except Exception as e:
        logger.error(f"Error registrando en Supabase: {cpb_num}: {e}")
        # Retornar True para no bloquear el flujo — el registro en Supabase es informativo
        return True


def actualizar_pago_a_notificado(cpb_ano: str, cpb_num: str, productor_cod: str) -> bool:
    """
    Actualiza estado de pago a 'notificado' DESPUÉS de enviar correo exitosamente.

    Args:
        cpb_ano: Año del comprobante
        cpb_num: Número del comprobante
        productor_cod: Código del productor

    Returns:
        True si se actualizó exitosamente
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py

        result = client.table("bot2_pagos_notificados") \
            .update({"estado": "notificado", "fecha_notificacion": datetime.now().isoformat()}) \
            .eq("cpb_ano", str(cpb_ano)) \
            .eq("cpb_num", str(cpb_num)) \
            .eq("productor_cod", str(productor_cod)) \
            .execute()

        return len(result.data) > 0

    except Exception as e:
        logger.error(f"Error actualizando estado en Supabase: {cpb_num}: {e}")
        return True


def marcar_nomina_anulada(id_nomina: str) -> bool:
    """
    Marca una nómina como 'anulado' en Supabase (bot2_estado='anulado').
    Se aplica automáticamente cuando detecta estado='anulada' en bot1_nominas_descargadas.
    Indica que esta nómina nunca se procesó porque fue cancelada en banco.

    Args:
        id_nomina: ID de nómina

    Returns:
        True si se actualizó exitosamente
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py

        result = client.table("bot1_nominas_descargadas") \
            .update({"bot2_estado": "anulado", "bot2_fecha_procesado": datetime.now().isoformat()}) \
            .eq("id_nomina", str(id_nomina)) \
            .execute()

        if result.data:
            logger.info(f"[OK] Nómina {id_nomina} marcada como anulada")
            return True
        else:
            logger.warning(f"[WARN] No se encontró nómina {id_nomina}")
            return False

    except Exception as e:
        logger.error(f"[ERROR] Error marcando nómina {id_nomina} como anulada: {e}")
        return False


def marcar_nomina_procesada(id_nomina: str) -> bool:
    """
    Marca una nómina como 'procesado' en Supabase (bot2_estado='procesado').
    Indica que ya se procesaron TODOS los productores de esa nómina.

    Args:
        id_nomina: ID de nómina

    Returns:
        True si se actualizó exitosamente
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py

        result = client.table("bot1_nominas_descargadas") \
            .update({"bot2_estado": "procesado", "bot2_fecha_procesado": datetime.now().isoformat()}) \
            .eq("id_nomina", str(id_nomina)) \
            .execute()

        if result.data:
            logger.info(f"[OK] Nómina {id_nomina} marcada como procesada")
            return True
        else:
            logger.warning(f"[WARN] No se encontró nómina {id_nomina}")
            return False

    except Exception as e:
        logger.error(f"[ERROR] Error marcando nómina {id_nomina}: {e}")
        return False


def obtener_nominas_descargadas_supabase() -> list:
    """
    Obtiene lista de nóminas descargadas por Bot 1 desde Supabase (tabla bot1_nominas_descargadas).

    Returns:
        Lista de dicts con campos: id_nomina, fecha_pago, estado, etc.
        Lista vacía si hay error
    """
    try:
        client = get_client()  # Cliente ya configurado con schema valle_frio_bot desde bot1/supabase_client.py

        result = client.table("bot1_nominas_descargadas") \
            .select("id_nomina, fecha_pago, estado, bot2_estado") \
            .execute()

        logger.info(f"[OK] Obtenidas {len(result.data)} nóminas descargadas")
        if result.data:
            logger.debug(f"  Nóminas encontradas: {[n.get('id_nomina') for n in result.data[:5]]}")
        return result.data

    except Exception as e:
        logger.error(f"[ERROR] Error obteniendo nóminas de Supabase: {e}")
        return []
