"""
Cliente de Supabase para el bot.
Schema explícito: "valle_frio_bot" (con underscore)
Credenciales: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY desde .env
NUNCA escribir en schema public bajo ninguna circunstancia.

Usa httpx directamente para POST/INSERT con header Accept-Profile.
"""

import os
import logging
import json
import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

logger = logging.getLogger(__name__)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_SCHEMA = "valle_frio_bot"

# Validaciones comentadas para permitir import en Prefect Cloud
# Las credenciales se verifican en runtime en el worker del Lenovo
# if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
#     raise ValueError("Faltan credenciales: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en .env")

# Cliente lazy - se inicializa en _get_client()
_client: Client = None

def _get_client() -> Client:
    """Inicializa el cliente Supabase de forma lazy (cuando se usa, no al importar)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("Faltan credenciales: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en .env")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        # CRÍTICO: Establecer AMBOS headers para SELECT y para INSERT/UPDATE/DELETE
        _client.postgrest.headers["Accept-Profile"] = SUPABASE_SCHEMA   # Para SELECT
        _client.postgrest.headers["Content-Profile"] = SUPABASE_SCHEMA  # Para INSERT/UPDATE/DELETE
        logger.info(f"Cliente Supabase inicializado con schema: {SUPABASE_SCHEMA}")
    return _client


def get_client() -> Client:
    """Retorna el cliente de Supabase con schema valle-frio-bot."""
    return _get_client()


def verificar_cartola_transaccion(num_transaccion: str) -> bool:
    """
    Verifica si una transacción ya fue descargada.

    Args:
        num_transaccion: Número de transacción del banco

    Returns:
        True si ya existe, False si es nueva
    """
    try:
        client = _get_client()
        result = client.table("bot1_cartola_transacciones") \
            .select("num_transaccion") \
            .eq("num_transaccion", num_transaccion) \
            .execute()
        return len(result.data) > 0
    except Exception as e:
        raise Exception(f"Error verificando cartola: {e}")


def insertar_cartola_transaccion(num_transaccion: str, fecha_contable, monto: float) -> bool:
    """
    Inserta una nueva transacción de cartola directamente en la tabla.

    Args:
        num_transaccion: Número de transacción
        fecha_contable: Fecha contable (para saber en qué carpeta guardar)
        monto: Monto de la transacción

    Returns:
        True si se insertó exitosamente
    """
    try:
        client = _get_client()
        client.table("bot1_cartola_transacciones").insert({
            "num_transaccion": num_transaccion,
            "fecha_contable": str(fecha_contable),
            "monto": monto
        }).execute()
        return True
    except Exception as e:
        raise Exception(f"Error insertando cartola: {e}")


def verificar_nomina(id_nomina: str) -> dict | None:
    """
    Verifica si una nómina ya fue descargada.

    Args:
        id_nomina: ID único de la nómina

    Returns:
        Registro de la nómina si existe, None si es nueva
    """
    try:
        client = _get_client()
        result = client.table("bot1_nominas_descargadas") \
            .select("*") \
            .eq("id_nomina", id_nomina) \
            .execute()
        if len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        raise Exception(f"Error verificando nómina: {e}")


def insertar_nomina(id_nomina: str, fecha_carga, fecha_pago, estado: str = "parcial") -> bool:
    """
    Inserta una nómina como 'parcial' usando RPC.

    Args:
        id_nomina: ID único de la nómina
        fecha_carga: Fecha de carga del PDF
        fecha_pago: Fecha de pago (de la nómina)
        estado: 'parcial' por defecto

    Returns:
        True si se insertó exitosamente
    """
    try:
        client = _get_client()
        client.rpc(
            "insertar_nomina",
            {
                "p_id_nomina": id_nomina,
                "p_fecha_carga": str(fecha_carga),
                "p_fecha_pago": str(fecha_pago),
                "p_estado": estado
            }
        ).execute()
        return True
    except Exception as e:
        raise Exception(f"Error insertando nómina: {e}")


def obtener_nominas_parciales():
    """Obtiene todas las nóminas con estado 'parcial' o 'pendiente' de cualquier fecha."""
    try:
        client = _get_client()
        # Obtener 'parcial' o 'pendiente'
        result_parcial = client.table("bot1_nominas_descargadas") \
            .select("*") \
            .eq("estado", "parcial") \
            .execute()
        result_pendiente = client.table("bot1_nominas_descargadas") \
            .select("*") \
            .eq("estado", "pendiente") \
            .execute()

        all_data = (result_parcial.data if result_parcial.data else []) + \
                   (result_pendiente.data if result_pendiente.data else [])
        return all_data
    except Exception as e:
        logger.error(f"Error obteniendo nóminas parciales/pendientes: {e}")
        return []


def actualizar_nomina_estado(id_nomina: str, estado: str, ruta_drive: str = None) -> bool:
    """
    Actualiza el estado de una nómina usando RPC.

    Args:
        id_nomina: ID único de la nómina
        estado: 'parcial' o 'completo'
        ruta_drive: Ruta en Drive donde se guardó (no implementado en RPC aún)

    Returns:
        True si se actualizó exitosamente
    """
    try:
        client = _get_client()
        client.rpc(
            "actualizar_nomina",
            {
                "p_id_nomina": id_nomina,
                "p_estado": estado
            }
        ).execute()
        return True
    except Exception as e:
        raise Exception(f"Error actualizando nómina: {e}")
