#!/usr/bin/env python3
"""
Bot 1 Flow para Prefect
Descarga de Cartolas y Nóminas del Banco Consorcio
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar bot1 al path
bot1_path = str(Path(__file__).parent.parent.parent / "bot1")
sys.path.insert(0, bot1_path)

from prefect import flow, task, get_run_logger


@task(name="ejecutar-bot1-task")
async def execute_bot1_task(fecha_testing: str = None):
    """Tarea que ejecuta Bot 1"""
    logger = get_run_logger()

    if not fecha_testing:
        fecha_testing = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Ejecutando Bot 1 para fecha: {fecha_testing}")

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
    bot1_flow()
