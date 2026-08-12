import logging
import asyncio
from pathlib import Path
from datetime import datetime
from config import TEMP_DOWNLOAD_PATH, CARTOLAS_PATH, BANCO_URL_LOGIN

logger = logging.getLogger(__name__)


async def paso_1_descargar_cartola(page, fecha_busqueda=None):
    """
    PASO 1: Descargar cartola de Saldos y movimientos.

    Navega: Cuentas > Saldos y movimientos
    Si no hay datos para hoy, intenta con día anterior.
    """
    logger.info("PASO 1: Descargando cartola (Saldos y movimientos)...")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Click en "Cuentas" del menú superior
        await page.wait_for_selector("nav a:has-text('Cuentas'), [role='tablist'] a:has-text('Cuentas')", timeout=30000)
        await asyncio.sleep(2)
        await page.click("nav a:has-text('Cuentas'), [role='tablist'] a:has-text('Cuentas')", timeout=10000)
        await asyncio.sleep(2)
        logger.info("Click en menú 'Cuentas'")

        # Esperar submenu y click en "Saldos y movimientos"
        await page.wait_for_selector("a:has-text('Saldos y movimientos')", timeout=10000)
        await asyncio.sleep(1)
        await page.click("a:has-text('Saldos y movimientos')", timeout=10000)
        await asyncio.sleep(3)
        logger.info("Navegando a Saldos y movimientos")

        # Esperar que cargue el selector de cuenta
        await page.wait_for_selector("input[name='numeroCuenta']", timeout=10000)
        await asyncio.sleep(1)
        logger.info("Selector de cuenta cargado")

        # Seleccionar cuenta CLP (4210026191)
        await page.click("input[name='numeroCuenta']", timeout=5000)
        await asyncio.sleep(0.8)
        logger.info("Abriendo dropdown de cuentas")

        await page.click("div[data-value*='4210026191']", timeout=5000)
        await asyncio.sleep(1.2)
        logger.info("Cuenta CLP seleccionada (4210026191)")

        # Esperar que cargue el formulario de búsqueda
        await page.wait_for_selector("button:has-text('Buscar')", timeout=10000)
        await asyncio.sleep(1)
        logger.info("Formulario de búsqueda cargado")

        # NO cambiar fechas - descargar TODO el reporte sin filtrar por fecha
        # El banco devuelve sus "últimos movimientos" por defecto (típicamente últimos 30-90 días)
        logger.info("Descargando reporte completo sin filtro de fecha")

        # Click en "Buscar"
        await page.click("button:has-text('Buscar')", timeout=5000)
        await asyncio.sleep(5)
        logger.info("Click en Buscar")

        # Esperar al botón Descargar
        try:
            await page.wait_for_selector("button:has-text('Descargar')", timeout=15000)
            await asyncio.sleep(1)
        except:
            logger.warning(f"No hay datos para {fecha_str}")
            return None

        # Click en el dropdown "Descargar"
        await page.click("button:has-text('Descargar')", timeout=5000)
        await asyncio.sleep(1)
        logger.info("Abriendo dropdown de Descargar")

        # Esperar a que aparezca "EXCEL"
        await page.wait_for_selector("text=EXCEL", timeout=5000)
        await asyncio.sleep(0.8)
        logger.info("Opciones de descarga visibles")

        # Click en "EXCEL"
        try:
            async with page.expect_download() as download_info:
                await page.click("text=EXCEL", timeout=5000)
                await asyncio.sleep(1)
            logger.info("Click en EXCEL")
        except Exception as e:
            logger.error(f"Error al descargar EXCEL: {e}")
            raise

        # Guardar el archivo descargado
        download = await download_info.value
        fecha_str_file = fecha_busqueda.strftime("%Y%m%d")

        # Asegurar que el directorio existe
        CARTOLAS_PATH.mkdir(parents=True, exist_ok=True)
        cartola_path = CARTOLAS_PATH / f"cartola_{fecha_str_file}.xlsx"

        try:
            await download.save_as(str(cartola_path))
        except PermissionError:
            # Si el archivo está en uso, usar nombre temporal
            cartola_path = CARTOLAS_PATH / f"cartola_{fecha_str_file}_temp.xlsx"
            await download.save_as(str(cartola_path))
            logger.warning(f"Archivo anterior en uso, guardado como temporal")

        logger.info(f"Cartola descargada: {cartola_path}")

        return cartola_path

    except Exception as e:
        logger.error(f"Error descargando cartola: {e}")
        raise
