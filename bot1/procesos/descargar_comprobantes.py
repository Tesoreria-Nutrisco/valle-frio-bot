import logging
import asyncio
from pathlib import Path
from datetime import datetime
from config import TEMP_DOWNLOAD_PATH, BANCO_URL_LOGIN

logger = logging.getLogger(__name__)

# Contador de intentos fallidos consecutivos para evitar loops infinitos
MAX_REINTENTOS_TIMEOUT = 3
TIMEOUT_DESCARGA = 20000


def normalizar_rut(rut):
    """Normaliza RUT: XX.XXX.XXX-X → XXXXXXXX-X"""
    return rut.replace(".", "")


async def paso_3_descargar_comprobante_rut(page, rut, fecha_pago, paso_0_login_fn=None, browser=None):
    """
    Descarga un comprobante individual para un RUT específico.
    CON RECOVERY: si hay timeout/caída del servidor, cierra página y abre nueva + login.

    Navega a Pago Nómina > Consultar > Consulta histórica
    Filtra por RUT + Convenio + rango de fecha (día actual)
    Descarga el PDF del comprobante

    Args:
        page: Página de Playwright
        rut: RUT a descargar
        fecha_pago: Fecha del pago
        paso_0_login_fn: Función async para re-hacer login si hay timeout
        browser: Browser de Playwright (para crear nueva página en caso de timeout)
    """
    logger.info(f"Descargando comprobante para RUT: {rut}")

    reintentos_timeout = 0
    page_ref = {'page': page}  # Referencia mutable para poder actualizar page en timeout

    while reintentos_timeout < MAX_REINTENTOS_TIMEOUT:
        try:
            page = page_ref['page']  # Usar la página actual (puede haber sido actualizada)
            logger.info("Verificando que estamos en Consulta histórica...")
            await asyncio.sleep(1)

            # Hacer click en el header "Consulta Histórica" para expandir el formulario
            try:
                await page.click("a:has-text('Consulta Histórica'), [ng-click*='openFilters']", timeout=5000)
                await asyncio.sleep(2)
                logger.info("Formulario expandido")
            except Exception as e:
                logger.warning(f"No se pudo hacer click en header: {e}")

            # Usar JavaScript para encontrar y verificar inputs
            inputs_info = await page.evaluate("""
                () => {
                    const inputs = document.querySelectorAll('input');
                    return Array.from(inputs).map((inp, idx) => ({
                        index: idx,
                        type: inp.type,
                        name: inp.name,
                        id: inp.id,
                        placeholder: inp.placeholder,
                        value: inp.value,
                        visible: inp.offsetParent !== null
                    }));
                }
            """)

            logger.info(f"Inputs encontrados: {len(inputs_info)}")
            for inp in inputs_info[:5]:
                logger.info(f"  Input {inp['index']}: type={inp['type']}, name={inp['name']}, placeholder={inp['placeholder']}, visible={inp['visible']}")

            await asyncio.sleep(0.5)

            # Llenar RUT haciendo click y escribiendo (más confiable con Angular)
            try:
                # Hacer click en el input de RUT por nombre
                await page.click("input[name='rutBeneficiario']", timeout=5000)
                await asyncio.sleep(0.5)

                # Limpiar el campo
                await page.keyboard.press("Control+A")
                await asyncio.sleep(0.2)

                # Escribir el RUT
                await page.keyboard.type(rut)
                await asyncio.sleep(0.8)
                logger.info(f"RUT beneficiario ingresado: {rut}")

            except Exception as e:
                logger.error(f"Error ingresando RUT: {e}")
                raise

            # Seleccionar Convenio - buscar por texto "Selecciona Convenio"
            try:
                # Usar JavaScript para encontrar y hacer click en el elemento que contiene "Selecciona Convenio"
                convenio_clicked = await page.evaluate("""
                    () => {
                        // Buscar TODOS los elementos que contienen "Selecciona Convenio"
                        const allElements = document.querySelectorAll('*');
                        for (let el of allElements) {
                            // Verificar que el texto sea exactamente "Selecciona Convenio" (not children)
                            if (el.childNodes.length > 0) {
                                let hasText = false;
                                for (let node of el.childNodes) {
                                    if (node.nodeType === 3 && node.textContent.includes('Selecciona Convenio')) {
                                        hasText = true;
                                        break;
                                    }
                                }
                                if (hasText) {
                                    // Hacer click en el elemento padre (probablemente el dropdown)
                                    el.parentElement.click();
                                    return 'clicked';
                                }
                            }
                        }
                        return 'not found';
                    }
                """)
                logger.info(f"Convenio click: {convenio_clicked}")
                await asyncio.sleep(1.5)

                # Buscar y hacer click en la opción "517"
                try:
                    await page.click("md-option:has-text('517')", timeout=5000)
                    logger.info("Convenio 517 seleccionado")
                except:
                    # Fallback: buscar cualquier elemento con "517"
                    await page.click("text=517", timeout=5000)
                    logger.info("Convenio 517 seleccionado (alternativa)")

            except Exception as e:
                logger.warning(f"Error seleccionando convenio: {e}")

            # Llenar AMBAS fechas (Desde y Hasta) con fecha_pago exacta
            fecha_str = fecha_pago.strftime("%d/%m/%Y") if fecha_pago else datetime.now().strftime("%d/%m/%Y")
            try:
                await page.evaluate(f"""
                    () => {{
                        const inputs = document.querySelectorAll('input.md-datepicker-input');
                        // Llenar Desde (input[0])
                        if (inputs.length >= 1) {{
                            inputs[0].value = '{fecha_str}';
                            inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                        // Llenar Hasta (input[1])
                        if (inputs.length >= 2) {{
                            inputs[1].value = '{fecha_str}';
                            inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inputs[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                """)
                await asyncio.sleep(0.8)
                logger.info(f"Fechas ingresadas: {fecha_str}")
            except Exception as e:
                logger.warning(f"Error llenando fechas: {e}")

            # Click en botón "Filtrar" (es un <a> tag, no button)
            try:
                await page.click("a:has-text('Filtrar'), a.btn-filtrar", timeout=5000)
                await asyncio.sleep(2)
                logger.info("Click en 'Filtrar'")
            except Exception as e:
                logger.warning(f"Error en click Filtrar: {e}")

            logger.info("Esperando resultados...")
            await asyncio.sleep(2)

            # Descargar PDF - debuggear y buscar botón
            logger.info("Buscando botón Descargar...")

            # Primero, listar todos los botones para ver qué hay
            botones_info = await page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    return Array.from(buttons).map(btn => ({
                        text: btn.textContent.trim(),
                        class: btn.className,
                        visible: btn.offsetParent !== null
                    }));
                }
            """)
            logger.info(f"Botones en la página: {botones_info}")

            # Hacer click en el <strong> que contiene "Descargar" (o su padre)
            async with page.expect_download(timeout=TIMEOUT_DESCARGA) as download_info:
                descargar_clicked = await page.evaluate("""
                    () => {
                        // Buscar el elemento <strong> con "Descargar"
                        const strongs = document.querySelectorAll('strong');
                        for (let strong of strongs) {
                            if (strong.textContent.trim() === 'Descargar') {
                                // Hacer click en el padre (probablemente <a> o <button>)
                                let parent = strong.parentElement;
                                if (parent) {
                                    parent.click();
                                    return 'clicked parent: ' + parent.tagName;
                                } else {
                                    strong.click();
                                    return 'clicked strong';
                                }
                            }
                        }
                        return 'not found';
                    }
                """)
                logger.info(f"Resultado: {descargar_clicked}")
                await asyncio.sleep(1)

            logger.info("PDF descargado")

            # Guardar el archivo
            download = await download_info.value
            rut_normalizado = normalizar_rut(rut)
            fecha_str_file = fecha_pago.strftime("%Y%m%d") if fecha_pago else datetime.now().strftime("%Y%m%d")
            comprobante_path = TEMP_DOWNLOAD_PATH / f"comprobante_{fecha_str_file}_{rut_normalizado}.pdf"

            await download.save_as(str(comprobante_path))
            logger.info(f"✓ Comprobante descargado: {comprobante_path}")

            return comprobante_path

        except Exception as e:
            # Detectar si es un timeout (puede ser asyncio.TimeoutError o str que contiene "Timeout")
            es_timeout = isinstance(e, asyncio.TimeoutError) or "Timeout" in str(type(e).__name__) or "timeout" in str(e).lower()

            if es_timeout:
                logger.error(f"⏱️ TIMEOUT en descarga (intento {reintentos_timeout + 1}/{MAX_REINTENTOS_TIMEOUT}): {e}")
                reintentos_timeout += 1

                # Detectar si hay modal de "Servicio fuera de línea"
                try:
                    modal_existe = await page.evaluate("""
                        () => {
                            // Buscar modal con "Servicio fuera de línea"
                            const modals = document.querySelectorAll('[role="dialog"], .modal, [class*="modal"]');
                            for (let modal of modals) {
                                if (modal.textContent.includes('Servicio fuera de línea') ||
                                    modal.textContent.includes('Error') ||
                                    modal.textContent.includes('timeout')) {
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)

                    if modal_existe:
                        logger.warning("Modal de error detectado, intentando cerrar...")
                        try:
                            # Hacer click en botón "Entendido" o similar
                            await page.click("button:has-text('Entendido'), button:has-text('Aceptar'), button:has-text('OK')", timeout=5000)
                            await asyncio.sleep(2)
                            logger.info("Modal cerrado")
                        except Exception as close_e:
                            logger.warning(f"No se pudo cerrar modal: {close_e}")
                except Exception as modal_e:
                    logger.warning(f"Error detectando modal: {modal_e}")

                # Si hay intentos disponibles, cerrar página y abrir nueva + login
                if reintentos_timeout < MAX_REINTENTOS_TIMEOUT and paso_0_login_fn and browser:
                    logger.info(f"Cerrando página y abriendo nueva (intento {reintentos_timeout}/{MAX_REINTENTOS_TIMEOUT})...")
                    try:
                        # Cerrar página vieja
                        await page.close()
                        logger.info("Página vieja cerrada")

                        # Abrir página nueva
                        new_page = await browser.new_page()
                        new_page.set_default_timeout(30000)
                        page_ref['page'] = new_page
                        page = new_page
                        logger.info("Página nueva abierta")

                        # Hacer login en la nueva página
                        await paso_0_login_fn(page)
                        logger.info("Login exitoso en nueva página")

                        # Navegar a Pago nómina > Consultar
                        logger.info("Navegando a Pago nómina > Consultar...")
                        try:
                            await page.evaluate("""
                                (function() {
                                    const links = document.querySelectorAll('a');
                                    for (let link of links) {
                                        if (!link.textContent.includes('Consultar')) continue;
                                        let parent = link.parentElement;
                                        for (let j = 0; j < 10; j++) {
                                            if (!parent) break;
                                            if (parent.textContent.includes('Pago nómina') &&
                                                parent.textContent.includes('Ingresar') &&
                                                !parent.textContent.includes('Botón de pago')) {
                                                link.click();
                                                return;
                                            }
                                            parent = parent.parentElement;
                                        }
                                    }
                                })()
                            """)
                            await asyncio.sleep(3)
                            logger.info("Navegación completada, reintentando descarga...")
                        except Exception as nav_e:
                            logger.warning(f"Error navegando a Pago nómina: {nav_e}")
                            logger.info("Continuando con reintento...")

                        continue  # Reintentar desde el principio
                    except Exception as recovery_e:
                        logger.error(f"Error en recovery (cerrar/abrir página): {recovery_e}")
                        raise
                else:
                    if not browser:
                        logger.warning("Browser no disponible para recovery, saltando RUT")
                    logger.error(f"Max reintentos alcanzados ({MAX_REINTENTOS_TIMEOUT})")
                    return None

            else:
                # No es timeout, es otro error
                logger.error(f"✗ Error descargando comprobante para RUT {rut}: {e}")
                raise

    # Fuera del while: si llegamos aquí, fue timeout máximo
    logger.error(f"No se pudo descargar comprobante para RUT {rut} tras {MAX_REINTENTOS_TIMEOUT} intentos")
    return None


async def paso_3_descargar_todos_comprobantes(page, ruts_unicos, fecha_pago, drive_service=None, folder_id_comprobantes=None, paso_0_login_fn=None, browser=None):
    """
    PASO 3: Descargar comprobantes individuales para cada RUT.
    CON RECOVERY: si hay timeout, cierra página y abre nueva + login.

    Por cada RUT único encontrado en la nómina, descarga su comprobante individual
    con la fecha_pago exacta (no un rango de fechas).

    Si drive_service y folder_id_comprobantes se proporcionan, verifica si el
    comprobante ya existe en Drive antes de descargar (deduplicación para nóminas 'parcial').

    Args:
        paso_0_login_fn: Función async para re-hacer login si hay timeout
        browser: Browser de Playwright (para crear nueva página en caso de timeout)
    """
    logger.info(f"PASO 3: Descargando comprobantes para {len(ruts_unicos)} RUTs...")

    comprobantes_descargados = []

    for idx, rut in enumerate(ruts_unicos, 1):
        logger.info(f"Procesando RUT {idx}/{len(ruts_unicos)}: {rut}")
        try:
            # Si tenemos acceso a Drive, verificar si el comprobante ya existe
            if drive_service and folder_id_comprobantes:
                rut_normalizado = rut.replace(".", "").replace("-", "")
                fecha_str_file = fecha_pago.strftime("%Y%m%d") if fecha_pago else datetime.now().strftime("%Y%m%d")
                expected_filename = f"comprobante_consorcio_{fecha_str_file}_{rut_normalizado}.pdf"

                # Buscar si el archivo ya existe en la carpeta
                query = f"'{folder_id_comprobantes}' in parents and name='{expected_filename}' and trashed=false"
                results = drive_service.files().list(q=query, spaces='drive', pageSize=1).execute()

                if results.get('files'):
                    logger.info(f"✓ Comprobante ya existe en Drive para RUT {rut}, saltando descarga")
                    comprobantes_descargados.append((rut, None))
                    continue

            comprobante_path = await paso_3_descargar_comprobante_rut(
                page, rut, fecha_pago, paso_0_login_fn=paso_0_login_fn, browser=browser
            )
            # Actualizar page por si fue cambiada en timeout recovery
            page = page  # No se modifica aquí, pero está disponible si cambió
            comprobantes_descargados.append((rut, comprobante_path))
        except Exception as e:
            logger.error(f"Error con RUT {rut}, continuando con siguiente...")
            continue

    logger.info(f"✓ Se descargaron {len(comprobantes_descargados)}/{len(ruts_unicos)} comprobantes")

    if not comprobantes_descargados:
        raise ValueError("No se descargó ningún comprobante")

    return comprobantes_descargados
