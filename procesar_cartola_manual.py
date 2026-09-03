#!/usr/bin/env python3
"""
Script para procesar cartolas históricas manualmente (descargadas desde banco).
Útil cuando Bot 1 no puede descargar automáticamente.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Agregar bot1 al path
sys.path.insert(0, str(Path(__file__).parent / "bot1"))

from procesos.procesar_cartola import paso_1_5_procesar_cartola


async def procesar_cartola_manual(archivo_path: str):
    """
    Procesa un archivo de cartola descargado manualmente.

    Args:
        archivo_path: Ruta al archivo XLS/XLSX de cartola
    """
    archivo = Path(archivo_path)

    if not archivo.exists():
        logger.error(f"Archivo no encontrado: {archivo}")
        return False

    logger.info(f"Procesando cartola: {archivo.name}")
    logger.info("=" * 80)

    try:
        filas_nuevas = await paso_1_5_procesar_cartola(archivo)

        logger.info("=" * 80)
        logger.info(f"✓ Procesamiento completado")
        logger.info(f"✓ Se insertaron {len(filas_nuevas)} transacciones nuevas en Supabase")

        if filas_nuevas:
            logger.info("\nTransacciones procesadas:")
            for fila in filas_nuevas[:5]:  # Mostrar primeras 5
                logger.info(f"  - {fila.get('num_transaccion')}: {fila.get('fecha_contable')} - ${fila.get('monto')}")
            if len(filas_nuevas) > 5:
                logger.info(f"  ... y {len(filas_nuevas) - 5} más")

        return True

    except Exception as e:
        logger.error(f"Error procesando cartola: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Uso: python procesar_cartola_manual.py <ruta_archivo>")
        logger.error("Ejemplo: python procesar_cartola_manual.py 'C:\\Users\\jpmunoz\\Downloads\\Cartola_historica_CLP_4210026191_20260903_1151.xls'")
        sys.exit(1)

    archivo_path = sys.argv[1]
    exito = asyncio.run(procesar_cartola_manual(archivo_path))
    sys.exit(0 if exito else 1)
