#!/usr/bin/env python3
"""
Script de prueba SOLO para Paso 3 - Descargar comprobantes
Permite probar con RUTs específicos sin ejecutar Pasos 1 y 2
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from config import LOG_PATH, TEMP_DOWNLOAD_PATH
from procesos.login import paso_0_login
from procesos.descargar_nomina import paso_2_descargar_nomina
from procesos.descargar_comprobantes import paso_3_descargar_todos_comprobantes

# Configurar logging
log_file = LOG_PATH / f"test_paso3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def test_paso3(ruts_a_probar=None):
    """
    Prueba solo el Paso 3 con RUTs específicos.

    Args:
        ruts_a_probar: Lista de RUTs a descargar comprobantes
                      Ej: ['76.334.187-9', '76.763.393-9']
    """
    if ruts_a_probar is None:
        ruts_a_probar = ['76.334.187-9', '76.763.393-9', '76.796.662-8', '77.713.645-3']

    logger.info("=" * 80)
    logger.info("TEST: SOLO PASO 3 - Descargar Comprobantes")
    logger.info("=" * 80)
    logger.info(f"RUTs a probar: {ruts_a_probar}")
    logger.info(f"Fecha: {datetime.now().strftime('%Y-%m-%d')}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            page.set_default_timeout(30000)

            # PASO 0: Login
            logger.info("PASO 0: Login...")
            await paso_0_login(page)

            # Navegar a Consulta Histórica
            logger.info("Navegando a Pago nómina > Consultar > Consulta histórica...")
            from config import BANCO_URL_LOGIN
            await page.goto(BANCO_URL_LOGIN + "/nominas/consultar", timeout=30000)
            await page.wait_for_selector("a:has-text('Consulta histórica')", timeout=15000)
            await page.click("a:has-text('Consulta histórica')", timeout=10000)
            await page.wait_for_selector("div:has-text('Consulta Histórica')", timeout=10000)
            logger.info("✓ En página de Consulta Histórica")

            # PASO 3: Descargar comprobantes
            logger.info("PASO 3: Descargando comprobantes...")
            fecha_hoy = datetime.now()

            comprobantes = await paso_3_descargar_todos_comprobantes(
                page, ruts_a_probar, fecha_hoy
            )

            logger.info("=" * 80)
            logger.info(f"✓ Se descargaron {len(comprobantes)}/{len(ruts_a_probar)} comprobantes")
            logger.info("=" * 80)

            for rut, path in comprobantes:
                logger.info(f"  - {rut}: {path}")

            await browser.close()

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"ERROR: {e}")
        logger.error("=" * 80)
        raise


if __name__ == "__main__":
    # RUTs de la foto enviada (del 5 de agosto)
    ruts_prueba = [
        '11.233.358-4',
        '13.683.040-6',
        '14.248.133-2',
        '15.939.685-1',
        '16.254.492-6',
        '17.131.376-7',
        '17.008.810-3',
        '19.008.810-3',
        '76.022.442-1',
        '76.033.522-3',
        '76.197.861-6',
        '76.212.570-6'
    ]

    asyncio.run(test_paso3(ruts_prueba))
