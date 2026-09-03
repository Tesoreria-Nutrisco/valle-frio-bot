#!/usr/bin/env python3
"""
Bot 1 Flow para Prefect
Descarga de Cartolas y Nóminas del Banco Consorcio
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar bot1 y este directorio al path
bot1_path = str(Path(__file__).parent.parent.parent / "bot1")
sys.path.insert(0, bot1_path)
flows_path = str(Path(__file__).parent)
if flows_path not in sys.path:
    sys.path.insert(0, flows_path)

from prefect import flow, task, get_run_logger
from prefect_secrets import cargar_secretos, conectar_logs

# Módulos de Bot 1 cuyos logs deben verse en la UI de Prefect.
# "procesos" cubre a sus submódulos (login, descargar_cartola, ...) por propagación.
MODULOS_BOT1 = ("run", "drive_utils", "supabase_client", "pdf_parser", "procesos")


@task(name="ejecutar-bot1-task")
async def execute_bot1_task(fecha_testing: str = None):
    """Tarea que ejecuta Bot 1"""
    logger = get_run_logger()

    if not fecha_testing:
        fecha_testing = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Ejecutando Bot 1 para fecha: {fecha_testing}")

    # Poblar el entorno desde Prefect ANTES de importar bot1.config
    await cargar_secretos()
    conectar_logs(*MODULOS_BOT1)

    try:
        from bot1.run import BotConsorcio
        bot = BotConsorcio(fecha_testing=datetime.strptime(fecha_testing, "%Y-%m-%d"))
        resultado = await bot.ejecutar()
        return resultado
    except Exception as e:
        logger.error(f"Error en Bot 1: {e}", exc_info=True)
        raise


@flow(name="valle-frio-bot-flow", description="Bot 1 - Descarga de cartolas y nóminas")
async def bot1_flow(fecha_testing: Optional[str] = None):
    """
    Flow principal de Bot 1 para Prefect

    Parameters:
        fecha_testing: Fecha para testing (default: hoy). Formato: YYYY-MM-DD
    """
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("INICIANDO BOT 1 - DESCARGA DE CARTOLAS Y NÓMINAS")
    logger.info("=" * 80)

    resultado = await execute_bot1_task(fecha_testing)

    logger.info("=" * 80)
    logger.info("BOT 1 COMPLETADO")
    logger.info("=" * 80)

    return resultado


if __name__ == "__main__":
    import asyncio
    asyncio.run(bot1_flow())
