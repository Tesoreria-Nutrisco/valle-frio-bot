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
        client = get_client()
        client.postgrest.headers["Accept-Profile"] = SUPABASE_SCHEMA

        result = client.table("bot2_pagos_notificados") \
            .select("id") \
            .eq("cpb_ano", str(cpb_ano)) \
            .eq("cpb_num", str(cpb_num)) \
            .eq("productor_cod", str(productor_cod)) \
            .eq("estado", "notificado") \
            .execute()

        return len(result.data) > 0

    except Exception as e:
        logger.warning(f"Error verificando duplicado {cpb_num}: {e}")
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
        client = get_client()
        client.postgrest.headers["Accept-Profile"] = SUPABASE_SCHEMA

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

        logger.info(f"[OK] Pago registrado: {cpb_num} | ${monto} | estado={estado}")
        return True

    except Exception as e:
        logger.error(f"Error registrando pago {cpb_num}: {e}")
        return False


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
        client = get_client()
        client.postgrest.headers["Accept-Profile"] = SUPABASE_SCHEMA

        result = client.table("bot2_pagos_notificados") \
            .update({"estado": "notificado", "fecha_notificacion": datetime.now().isoformat()}) \
            .eq("cpb_ano", str(cpb_ano)) \
            .eq("cpb_num", str(cpb_num)) \
            .eq("productor_cod", str(productor_cod)) \
            .execute()

        return len(result.data) > 0

    except Exception as e:
        logger.error(f"Error actualizando pago {cpb_num} a notificado: {e}")
        return False
