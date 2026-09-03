#!/usr/bin/env python3
"""
Bot 2 Flow para Prefect
Reconciliación de Egresos Softland vs Cartola Bancaria
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar bot2 y este directorio al path
bot2_path = str(Path(__file__).parent.parent.parent / "bot2")
sys.path.insert(0, bot2_path)
flows_path = str(Path(__file__).parent)
if flows_path not in sys.path:
    sys.path.insert(0, flows_path)

from prefect import flow, task, get_run_logger
from prefect_secrets import cargar_secretos, conectar_logs

# Módulos de Bot 2 cuyos logs deben verse en la UI de Prefect.
MODULOS_BOT2 = (
    "run",
    "supabase_bot2",
    "supabase_client",
    "notificador",
    "matcher",
    "gaussdb_client",
    "cartola_cleaner",
    "drive_utils",
)


@task(name="ejecutar-bot2-task")
async def execute_bot2_task(fecha_prueba: str = None):
    """Tarea que ejecuta Bot 2"""
    logger = get_run_logger()

    if not fecha_prueba:
        fecha_prueba = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Ejecutando Bot 2 para fecha: {fecha_prueba}")

    # Poblar el entorno desde Prefect ANTES de importar bot2.config
    await cargar_secretos()
    conectar_logs(*MODULOS_BOT2)

    try:
        from bot2.run import main as bot2_main
        resultado = bot2_main(fecha_prueba)
        return resultado
    except Exception as e:
        logger.error(f"Error en Bot 2: {e}", exc_info=True)
        raise


@flow(name="bot2-reconciliation", description="Bot 2 - Reconciliación Softland vs Cartola")
async def bot2_flow(fecha_testing: Optional[str] = None):
    """
    Flow principal de Bot 2 para Prefect.

    Parameters:
        fecha_testing: Fecha para testing (default: hoy). Formato: YYYY-MM-DD
    """
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("INICIANDO BOT 2 - RECONCILIACIÓN")
    logger.info("=" * 80)

    resultado = await execute_bot2_task(fecha_testing)

    logger.info("=" * 80)
    logger.info("BOT 2 COMPLETADO")
    logger.info("=" * 80)

    return resultado


if __name__ == "__main__":
    import asyncio
    asyncio.run(bot2_flow())
