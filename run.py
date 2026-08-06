#!/usr/bin/env python3
"""
Bot de descarga de cartolas y comprobantes - Banco Consorcio

PUNTO DE ENTRADA: ejecuta este archivo para correr el bot completo.

Pasos:
  0. Login
  1. Descargar cartola
  2. Subir cartola a Drive
  3. Descargar nómina PDF
  4. Parsear PDF y extraer RUTs
  5. Descargar comprobantes individuales
  6. Subir comprobantes a Drive
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from config import (
    MODO_DRY_RUN, LOG_PATH, TEMP_DOWNLOAD_PATH,
    DRIVE_FOLDER_ID_CARTOLAS, DRIVE_FOLDER_ID_COMPROBANTES, BANCO_NOMBRE_CARPETA
)
from drive_utils import get_drive_service, get_carpeta_destino, upload_file
from pdf_parser import extraer_ruts_nomina
from procesos.login import paso_0_login
from procesos.descargar_cartola import paso_1_descargar_cartola
from procesos.descargar_nomina import paso_2_descargar_nomina
from procesos.descargar_comprobantes import paso_3_descargar_todos_comprobantes

# Configurar logging
log_file = LOG_PATH / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BotConsorcio:
    """Bot para automatizar descargas de cartolas y comprobantes del banco Consorcio."""

    def __init__(self, fecha_testing=None):
        self.browser = None
        self.page = None
        self.drive_service = None
        # Si no se especifica fecha, usa hoy
        if fecha_testing:
            self.fecha_hoy = fecha_testing
        else:
            self.fecha_hoy = datetime.now()

    async def ejecutar(self):
        """Ejecuta el flujo completo del bot."""
        logger.info("=" * 80)
        logger.info("INICIANDO BOT CONSORCIO")
        logger.info("=" * 80)
        logger.info(f"Fecha: {self.fecha_hoy.strftime('%Y-%m-%d')}")
        logger.info(f"Modo: {'DRY RUN' if MODO_DRY_RUN else 'PRODUCCIÓN'}")

        try:
            # Inicializar Playwright
            async with async_playwright() as p:
                self.browser = await p.chromium.launch(headless=False)
                self.page = await self.browser.new_page()
                # Aumentar timeout global
                self.page.set_default_timeout(30000)

                # Inicializar Google Drive
                self.drive_service = get_drive_service()

                # ========== PASO 0: Login ==========
                await paso_0_login(self.page)

                # ========== PASO 1: Descargar cartola ==========
                cartola_path = await paso_1_descargar_cartola(self.page, self.fecha_hoy)

                # ========== PASO 1.5: Subir cartola a Drive ==========
                if cartola_path:
                    logger.info("Subiendo cartola a Google Drive...")
                    TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                    folder_id = get_carpeta_destino(
                        self.drive_service,
                        DRIVE_FOLDER_ID_CARTOLAS,
                        BANCO_NOMBRE_CARPETA,
                        self.fecha_hoy,
                        TEAM_DRIVE_ID
                    )
                    file_name = f"cartola_{BANCO_NOMBRE_CARPETA}_{self.fecha_hoy.strftime('%Y%m%d')}.xlsx"
                    upload_file(self.drive_service, cartola_path, folder_id, file_name)
                    logger.info("✓ Cartola subida a Drive")
                else:
                    logger.info("⚠ No hay cartola para subir (sin movimientos del día)")

                # ========== PASO 2: Descargar nómina PDF ==========
                nomina_pdf_path = await paso_2_descargar_nomina(self.page, self.fecha_hoy)

                # ========== PASO 2.5: Parsear PDF y extraer RUTs ==========
                if nomina_pdf_path:
                    logger.info("Parseando PDF de nómina para extraer RUTs...")
                    ruts_unicos = extraer_ruts_nomina(nomina_pdf_path)
                    logger.info(f"Se encontraron {len(ruts_unicos)} RUTs únicos")
                else:
                    logger.warning("No hay PDF de nómina para procesar")
                    ruts_unicos = []

                # ========== PASO 3: Descargar comprobantes individuales ==========
                if ruts_unicos:
                    logger.info(f"Descargando comprobantes para {len(ruts_unicos)} RUTs...")
                    try:
                        comprobantes = await paso_3_descargar_todos_comprobantes(
                            self.page, ruts_unicos, self.fecha_hoy
                        )

                        # ========== PASO 3.5: Subir comprobantes a Drive ==========
                        if comprobantes:
                            logger.info("Subiendo comprobantes a Google Drive...")
                            TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                            folder_id_comprobantes = get_carpeta_destino(
                                self.drive_service,
                                DRIVE_FOLDER_ID_COMPROBANTES,
                                BANCO_NOMBRE_CARPETA,
                                self.fecha_hoy,
                                TEAM_DRIVE_ID
                            )

                            for rut, comprobante_path in comprobantes:
                                try:
                                    rut_normalizado = rut.replace(".", "").replace("-", "")
                                    file_name = f"comprobante_{BANCO_NOMBRE_CARPETA}_{self.fecha_hoy.strftime('%Y%m%d')}_{rut_normalizado}.pdf"
                                    upload_file(self.drive_service, comprobante_path, folder_id_comprobantes, file_name)
                                    logger.info(f"Comprobante subido para RUT {rut}")
                                except Exception as e:
                                    logger.error(f"Error subiendo comprobante para RUT {rut}: {e}")
                                    continue
                        else:
                            logger.warning("No se descargaron comprobantes")
                    except Exception as e:
                        logger.warning(f"PASO 3 (Comprobantes) falló: {e}")
                else:
                    logger.warning("No hay RUTs para descargar comprobantes")

                logger.info("=" * 80)
                logger.info("BOT COMPLETADO EXITOSAMENTE")
                logger.info("=" * 80)

        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"BOT FALLÓ: {e}")
            logger.error("=" * 80)
            raise

        finally:
            if self.browser:
                await self.browser.close()
                logger.info("Browser cerrado")


async def main(fecha_testing=None):
    """Punto de entrada principal."""
    bot = BotConsorcio(fecha_testing)
    await bot.ejecutar()


if __name__ == "__main__":
    asyncio.run(main())
