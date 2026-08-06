import logging
import asyncio
from config import BANCO_URL_LOGIN, BANCO_USUARIO, BANCO_CLAVE

logger = logging.getLogger(__name__)


async def paso_0_login(page):
    """
    PASO 0: Iniciar sesión en el banco.

    Selectores reales del banco:
    - Input RUT: #rut
    - Input Contraseña: #contraseña
    - Botón Submit: input[type="submit"][value="Ingresar"]
    """
    logger.info("PASO 0: Iniciando sesión en banco Consorcio...")

    try:
        await page.goto(BANCO_URL_LOGIN, wait_until="networkidle")
        logger.info(f"Navegando a {BANCO_URL_LOGIN}")

        # Esperar que el formulario esté visible
        await page.wait_for_selector("#rut", timeout=10000)
        logger.info("Formulario de login visible")

        # Llenar RUT (pausa humanizada)
        await page.fill("#rut", BANCO_USUARIO)
        await asyncio.sleep(0.8)  # Pausa después de llenar RUT
        logger.info(f"RUT ingresado: {BANCO_USUARIO}")

        # Llenar contraseña (pausa humanizada)
        await page.fill("#contraseña", BANCO_CLAVE)
        await asyncio.sleep(1.2)  # Pausa después de llenar contraseña
        logger.info("Contraseña ingresada")

        # Click en botón Ingresar (submit)
        await page.click('input[type="submit"][value="Ingresar"]', timeout=5000)
        await asyncio.sleep(2)  # Esperar a que procese el login
        logger.info("Click en botón Ingresar")

        # Esperar que seleccione la empresa (VALLE FRIO SPA)
        await page.wait_for_selector("md-radio-button:has-text('VALLE FRIO SPA')", timeout=10000)
        await asyncio.sleep(1)  # Pausa antes de seleccionar empresa
        logger.info("Seleccionando empresa VALLE FRIO SPA")

        await page.click("md-radio-button:has-text('VALLE FRIO SPA')", timeout=5000)
        await asyncio.sleep(1.5)  # Pausa después de seleccionar empresa
        logger.info("Empresa seleccionada")

        # Esperar redirección al dashboard
        await page.wait_for_url("**/dashboard**", timeout=15000)
        logger.info("✓ Login exitoso")

        return True

    except Exception as e:
        logger.error(f"✗ Error en login: {e}")
        raise
