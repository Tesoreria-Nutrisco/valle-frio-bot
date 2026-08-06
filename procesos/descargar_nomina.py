import logging
import asyncio
from pathlib import Path
from datetime import datetime
from config import TEMP_DOWNLOAD_PATH, BANCO_URL_LOGIN

logger = logging.getLogger(__name__)


async def paso_2_descargar_nomina(page, fecha_busqueda=None):
    """
    PASO 2: Descargar PDF de nómina (Estado de Firmas).

    Navega: Pagos > Pago Nómina > Consultar > Estado de Firmas
    Descarga el PDF.
    """
    logger.info("PASO 2: Descargando PDF de nómina (Estado de Firmas)...")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Click en "Pagos" del menú superior
        await page.wait_for_selector("nav a:has-text('Pagos'), [role='tablist'] a:has-text('Pagos')", timeout=30000)
        await asyncio.sleep(1)
        await page.click("nav a:has-text('Pagos'), [role='tablist'] a:has-text('Pagos')", timeout=10000)
        await asyncio.sleep(3)
        logger.info("Click en menú 'Pagos'")

        # Esperar a que aparezca "Consultar" bajo Pago nómina
        await page.wait_for_selector("a:has(span.ng-binding:has-text('Consultar'))", timeout=15000)
        await asyncio.sleep(1)
        logger.info("Menú de Pagos cargado")

        # Usar JavaScript pero SER MÁS ESPECÍFICO: buscar solo en la sección de Pagos
        await page.evaluate("""
            (function() {
                // Buscar específicamente el <a> que es hijo directo o cercano a "Pago nómina"
                const allAnchors = document.querySelectorAll('a');

                for (let i = 0; i < allAnchors.length; i++) {
                    const link = allAnchors[i];

                    // Verificar que este link sea "Consultar"
                    if (!link.textContent.includes('Consultar')) continue;

                    // Verificar que esté en la sección correcta (antes de "Botón de pago")
                    // Buscar hacia atrás en el DOM para encontrar "Pago nómina" antes de este link
                    let foundPagoNomina = false;
                    let parent = link.parentElement;

                    for (let j = 0; j < 10; j++) {
                        if (!parent) break;
                        if (parent.textContent.includes('Pago nómina') &&
                            parent.textContent.includes('Ingresar') &&
                            !parent.textContent.includes('Botón de pago')) {
                            foundPagoNomina = true;
                            break;
                        }
                        parent = parent.parentElement;
                    }

                    if (foundPagoNomina) {
                        link.click();
                        return;
                    }
                }
            })()
        """)
        await asyncio.sleep(3)
        logger.info("Click en 'Consultar' (Pago nómina)")

        # Estado de Firmas debería estar activo por defecto
        # Esperar tabla de nóminas
        await page.wait_for_selector("button.dropdown", timeout=10000)
        await asyncio.sleep(1)
        logger.info("Tabla de nóminas cargada")

        # Click en el dropdown de acciones
        await page.click("button.dropdown", timeout=5000)
        await asyncio.sleep(1)
        logger.info("Abriendo dropdown de acciones")

        # Click en "Descarga PDF"
        async with page.expect_download() as download_info:
            await page.click("a.dropdown-content-action:has-text('Descarga PDF')", timeout=5000)
            await asyncio.sleep(1)
        logger.info("Click en 'Descarga PDF'")

        # Guardar archivo
        download = await download_info.value
        fecha_str = fecha_busqueda.strftime("%Y%m%d")
        nomina_path = TEMP_DOWNLOAD_PATH / f"nomina_{fecha_str}.pdf"

        try:
            await download.save_as(str(nomina_path))
        except PermissionError:
            # Si el archivo está en uso, usar nombre temporal
            nomina_path = TEMP_DOWNLOAD_PATH / f"nomina_{fecha_str}_temp.pdf"
            await download.save_as(str(nomina_path))
            logger.warning(f"Archivo anterior en uso, guardado como temporal")

        logger.info(f"PDF de nómina descargado: {nomina_path}")

        return nomina_path

    except Exception as e:
        logger.error(f"Error descargando nómina: {e}")
        raise
