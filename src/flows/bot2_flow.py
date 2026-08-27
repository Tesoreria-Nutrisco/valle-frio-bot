#!/usr/bin/env python3
"""
Bot 2 Flow para Prefect
Reconciliación de Egresos Softland vs Cartola Bancaria
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar bot2 al path
bot2_path = str(Path(__file__).parent.parent.parent / "bot2")
sys.path.insert(0, bot2_path)

from prefect import flow, task, get_run_logger


@task(name="ejecutar-bot2-task")
def execute_bot2_task(fecha_prueba: str = None):
    """Tarea que ejecuta Bot 2"""
    logger = get_run_logger()

    if not fecha_prueba:
        fecha_prueba = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Ejecutando Bot 2 para fecha: {fecha_prueba}")

    try:
        from bot2.run import main as bot2_main
        resultado = bot2_main(fecha_prueba)
        return resultado
    except Exception as e:
        logger.error(f"Error en Bot 2: {e}", exc_info=True)
        raise


@flow(name="bot2-reconciliation", description="Bot 2 - Reconciliación Softland vs Cartola")
def bot2_flow(fecha_testing: Optional[str] = None):
    """
    Flow principal de Bot 2 para Prefect

    Parameters:
        fecha_testing: Fecha para testing (default: hoy). Formato: YYYY-MM-DD
    """
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("INICIANDO BOT 2 - RECONCILIACIÓN")
    logger.info("=" * 80)

    resultado = execute_bot2_task(fecha_testing)

    logger.info("=" * 80)
    logger.info("BOT 2 COMPLETADO")
    logger.info("=" * 80)

    return resultado


if __name__ == "__main__":
    bot2_flow()
