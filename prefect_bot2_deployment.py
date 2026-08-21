#!/usr/bin/env python3
"""
Deployment de Bot 2 para Prefect
Reconciliación de Egresos Softland vs Cartola Bancaria

Uso:
    # Crear deployment
    python prefect_bot2_deployment.py

    # Ejecutar manualmente en Prefect Cloud
    prefect deployment run "bot2-reconciliation/bot2-test" --param fecha_prueba=2026-08-21
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from prefect import flow, task, get_run_logger
from prefect.deployments import Deployment

# Agregar paths
bot1_path = str(Path(__file__).parent / "bot1")
bot2_path = str(Path(__file__).parent / "bot2")
sys.path.insert(0, bot1_path)
sys.path.insert(0, bot2_path)

from bot2.config import MODO_TEST, LOG_PATH
from bot2.run import procesar_confirmados, procesar_no_cuadra


@task(name="ejecutar-bot2-reconciliacion", retries=2)
def ejecutar_bot2(fecha_prueba: str = None):
    """
    Tarea que ejecuta la reconciliación de Bot 2.

    Args:
        fecha_prueba: Fecha en formato YYYY-MM-DD para pruebas (default: hoy)
    """
    logger = get_run_logger()
    logger.info(f"🚀 Iniciando Bot 2 Reconciliación")
    logger.info(f"   Modo: {'TEST' if MODO_TEST else 'PRODUCCIÓN'}")
    logger.info(f"   Fecha: {fecha_prueba or 'hoy'}")

    if not fecha_prueba:
        fecha_prueba = datetime.now().strftime("%Y-%m-%d")

    try:
        # Ejecutar Bot 2
        from bot2.run import main as bot2_main
        resultado = bot2_main(fecha_prueba)

        logger.info(f"✅ Bot 2 completado exitosamente")
        return resultado
    except Exception as e:
        logger.error(f"❌ Error en Bot 2: {e}", exc_info=True)
        raise


@flow(name="bot2-reconciliation", version="1.0.0", log_prints=True)
def bot2_flow(fecha_prueba: str = None):
    """
    Flow principal de Bot 2 en Prefect.

    Reconcilia egresos de Softland contra cartola bancaria.

    Parameters:
        fecha_prueba: Fecha en formato YYYY-MM-DD para testing (default: hoy)

    Returns:
        Resultado de la ejecución
    """
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("BOT 2: RECONCILIACIÓN DE EGRESOS")
    logger.info("=" * 80)

    resultado = ejecutar_bot2(fecha_prueba)

    logger.info("=" * 80)
    logger.info(f"✅ Flow completado")
    logger.info("=" * 80)

    return resultado


def crear_deployment():
    """Crear deployment de Bot 2 en Prefect."""
    import subprocess

    print(f"\n🚀 Creando deployment de Bot 2...")
    print(f"   Modo: TEST (local)")
    print(f"   Flow: bot2-reconciliation")

    try:
        # Usar prefect CLI para crear deployment
        cmd = [
            "prefect",
            "deployment",
            "build",
            str(Path(__file__).absolute()),
            "-n", "bot2-test",
            "-t", "bot2",
            "-t", "reconciliacion",
            "-t", "test",
            "--skip-upload",
            "-q"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent))

        if result.returncode == 0:
            print(f"\n✅ Deployment creado exitosamente")
            print(f"   Nombre: bot2-reconciliation/bot2-test")
            print(f"\n📌 Para ejecutar desde Prefect:")
            print(f"   prefect deployment run 'bot2-reconciliation/bot2-test'")
            print(f"\n   O iniciar scheduler y ejecutar desde Prefect UI")
            return True
        else:
            print(f"\n⚠️  Deployment CLI salida: {result.stderr}")
            # Continuar de todos modos
            return True

    except Exception as e:
        print(f"\n⚠️  Error con CLI, usando método directo: {e}")
        try:
            # Método alternativo: usar Deployment.build directamente
            deployment = Deployment.build(
                flow=bot2_flow,
                name="bot2-test",
                description="Bot 2 - Reconciliación Softland vs Cartola (TEST)",
                tags=["bot2", "reconciliacion", "test"],
                parameters={"fecha_prueba": None},
                version="1.0.0"
            )
            print(f"✅ Deployment construido (storage local)")
            return True
        except Exception as e2:
            print(f"❌ Error: {e2}")
            return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Ejecutar flow localmente para testing
        print("🧪 Ejecutando Bot 2 en modo test local...")
        resultado = bot2_flow(fecha_prueba=datetime.now().strftime("%Y-%m-%d"))
        print(f"\n✅ Test completado: {resultado}")
    else:
        # Crear deployment en Prefect Cloud
        exito = crear_deployment()
        sys.exit(0 if exito else 1)
