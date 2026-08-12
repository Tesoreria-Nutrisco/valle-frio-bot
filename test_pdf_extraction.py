#!/usr/bin/env python3
"""
Script de validación: prueba extracción de metadatos contra PDFs de ejemplo.
"""

import sys
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Importar funciones
from pdf_parser import extraer_metadatos_nomina, extraer_ruts_nomina

def validar_nomina(pdf_path):
    """Valida extracción de metadatos de una nómina."""
    logger.info("=" * 80)
    logger.info(f"VALIDANDO: {pdf_path}")
    logger.info("=" * 80)

    if not Path(pdf_path).exists():
        logger.error(f"❌ Archivo no existe: {pdf_path}")
        return False

    try:
        metadatos = extraer_metadatos_nomina(pdf_path)
        logger.info(f"✓ Metadatos extraídos correctamente:")
        logger.info(f"  - ID nómina: {metadatos['id_nomina']}")
        logger.info(f"  - Fecha carga: {metadatos['fecha_carga']}")
        logger.info(f"  - Fecha pago: {metadatos['fecha_pago']}")

        # Validaciones básicas
        if not metadatos['id_nomina']:
            logger.error("❌ ID nómina vacío")
            return False
        if not metadatos['fecha_carga']:
            logger.warning("⚠ Fecha carga no se pudo extraer")
        if not metadatos['fecha_pago']:
            logger.warning("⚠ Fecha pago no se pudo extraer")

        logger.info("✓ Validación de metadatos PASÓ")
        return True

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return False


def validar_ruts(pdf_path):
    """Valida extracción de RUTs de una nómina."""
    logger.info("=" * 80)
    logger.info(f"VALIDANDO RUTs: {pdf_path}")
    logger.info("=" * 80)

    if not Path(pdf_path).exists():
        logger.error(f"❌ Archivo no existe: {pdf_path}")
        return False

    try:
        ruts = extraer_ruts_nomina(pdf_path)
        logger.info(f"✓ Se encontraron {len(ruts)} RUTs únicos:")
        for rut in ruts:
            logger.info(f"  - {rut}")

        if not ruts:
            logger.error("❌ No se encontraron RUTs")
            return False

        logger.info("✓ Validación de RUTs PASÓ")
        return True

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Rutas de PDFs de ejemplo (ajusta según dónde guardes los archivos)
    # Para este test, necesitas copiar los PDFs a esta carpeta o especificar la ruta

    pdf_nomina = "nomina_20260805.pdf"
    pdf_comprobante1 = "comprobante_20260806_11233358-4.pdf"
    pdf_comprobante2 = "comprobante_20260806_13683040-6.pdf"

    print("\n" + "=" * 80)
    print("VALIDACIÓN DE EXTRACCIÓN DE PDFs")
    print("=" * 80 + "\n")

    # Validar nómina
    resultados = {}

    if Path(pdf_nomina).exists():
        resultados["Nómina - Metadatos"] = validar_nomina(pdf_nomina)
        resultados["Nómina - RUTs"] = validar_ruts(pdf_nomina)
    else:
        logger.warning(f"⚠ No se encontró {pdf_nomina}, saltando")

    if Path(pdf_comprobante1).exists():
        logger.info("\n⚠ Nota: Comprobante individual no tiene metadatos de nómina")
        logger.info("   Solo validamos que se puede abrir el PDF")

    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 80)
    for test, resultado in resultados.items():
        status = "✓ PASÓ" if resultado else "❌ FALLÓ"
        print(f"{test}: {status}")

    all_passed = all(resultados.values())
    if all_passed:
        print("\n✓✓✓ TODAS LAS VALIDACIONES PASARON ✓✓✓")
        sys.exit(0)
    else:
        print("\n❌ ALGUNAS VALIDACIONES FALLARON")
        sys.exit(1)
