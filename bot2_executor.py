#!/usr/bin/env python3
"""
Ejecutor de Bot 2 - Envoltorio para Prefect
Reconciliación de Egresos Softland vs Cartola Bancaria

Uso local:
    python bot2_executor.py [YYYY-MM-DD]

Uso en Prefect:
    prefect flow run bot2_executor.py:execute_bot2 --parameter fecha_prueba=2026-08-21
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agregar paths
bot1_path = str(Path(__file__).parent / "bot1")
bot2_path = str(Path(__file__).parent / "bot2")
sys.path.insert(0, bot1_path)
sys.path.insert(0, bot2_path)


def execute_bot2(fecha_prueba: str = None) -> Dict[str, Any]:
    """
    Ejecuta Bot 2 - Reconciliación Softland vs Cartola

    Args:
        fecha_prueba: Fecha en formato YYYY-MM-DD (default: hoy)

    Returns:
        Dict con resultado de la ejecución
    """
    logger.info("=" * 80)
    logger.info("BOT 2: RECONCILIACIÓN DE EGRESOS SOFTLAND vs CARTOLA")
    logger.info("=" * 80)

    if not fecha_prueba:
        fecha_prueba = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"📅 Fecha de prueba: {fecha_prueba}")

    try:
        # Importar y ejecutar Bot 2
        from bot2.run import main as bot2_main

        logger.info("🚀 Iniciando proceso de reconciliación...")
        resultado = bot2_main(fecha_prueba)

        logger.info("=" * 80)
        logger.info("✅ BOT 2 COMPLETADO EXITOSAMENTE")
        logger.info("=" * 80)

        return {
            "success": True,
            "fecha": fecha_prueba,
            "timestamp": datetime.now().isoformat(),
            "resultado": resultado
        }

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ ERROR EN BOT 2: {e}")
        logger.error("=" * 80, exc_info=True)

        return {
            "success": False,
            "fecha": fecha_prueba,
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


if __name__ == "__main__":
    # Modo CLI directo
    fecha = sys.argv[1] if len(sys.argv) > 1 else None

    logger.info(f"\n🧪 Ejecutando Bot 2 en modo test...")
    resultado = execute_bot2(fecha)

    if resultado["success"]:
        logger.info(f"\n✅ Ejecución exitosa")
        sys.exit(0)
    else:
        logger.error(f"\n❌ Ejecución fallida: {resultado.get('error')}")
        sys.exit(1)
