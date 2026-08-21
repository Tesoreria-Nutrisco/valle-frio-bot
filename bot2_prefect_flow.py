#!/usr/bin/env python3
"""
Bot 2 como Prefect Flow
Compatible con Prefect 3.7.5
"""

import sys
from pathlib import Path
from datetime import datetime

try:
    from prefect import flow, task, get_run_logger
except ImportError:
    print("Prefect no está instalado. Instalando...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "prefect==3.7.5"])
    from prefect import flow, task, get_run_logger


@task(name="ejecutar-bot2")
def execute_bot2_task(fecha_prueba: str = None):
    """Ejecuta Bot 2"""
    logger = get_run_logger()

    if not fecha_prueba:
        fecha_prueba = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"📅 Ejecutando Bot 2 para fecha: {fecha_prueba}")

    try:
        from bot2_executor import execute_bot2
        resultado = execute_bot2(fecha_prueba)
        return resultado
    except Exception as e:
        logger.error(f"❌ Error en Bot 2: {e}", exc_info=True)
        raise


@flow(name="bot2-reconciliation", description="Bot 2 - Reconciliación Softland vs Cartola")
def bot2_flow(fecha_prueba: str = None):
    """
    Flow de Bot 2 para Prefect

    Parameters:
        fecha_prueba: Fecha en formato YYYY-MM-DD (default: hoy)
    """
    logger = get_run_logger()
    logger.info("🚀 Iniciando Bot 2 Flow en Prefect")

    resultado = execute_bot2_task(fecha_prueba)

    logger.info("✅ Bot 2 Flow completado")
    return resultado


if __name__ == "__main__":
    # Ejecutar como script local
    import logging
    logging.basicConfig(level=logging.INFO)

    fecha = sys.argv[1] if len(sys.argv) > 1 else None
    print("🚀 Ejecutando Bot 2...")
    resultado = bot2_flow(fecha)
    print(f"✅ Completado: {resultado}")
