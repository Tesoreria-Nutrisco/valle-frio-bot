import logging
import asyncio
import time
from pathlib import Path
from datetime import datetime
from config import TEMP_DOWNLOAD_PATH, NOMINAS_PATH, BANCO_URL_LOGIN

logger = logging.getLogger(__name__)


async def obtener_nominas_con_montos(page, fecha_busqueda=None):
    """
    Lee la tabla de nóminas y extrae ID + Monto para cada nómina.

    Returns:
        Lista de dicts: [{'id_nomina': '1965892', 'monto': '73384191'}, ...]
    """
    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        fecha_str = fecha_busqueda.strftime("%d/%m/%Y")
        logger.info(f"Extrayendo nóminas con montos para fecha: {fecha_str}")

        # Extraer ID + Monto desde el DOM
        datos = await page.evaluate("""
            () => {
                const result = [];
                const filas = document.querySelectorAll('[ng-repeat*="transacciones"]');

                filas.forEach((fila) => {
                    // Buscar el ID (ng-click con agregarOperacionDetalle)
                    const idDiv = fila.querySelector('[ng-click*="agregarOperacionDetalle"]');
                    if (!idDiv) return;

                    const id = idDiv.textContent.trim();
                    if (!id.match(/^\\d{6,7}$/)) return;

                    // Buscar el monto (buscar celda con formato $ xxx.xxx.xxx)
                    const celdas = fila.querySelectorAll('[ng-repeat*="transacciones"] [ng-repeat], td, div[ng-repeat]');
                    let monto = null;

                    // Buscar en todo el texto de la fila el patrón de monto
                    const textoFila = fila.textContent;
                    const matchMonto = textoFila.match(/\\$\\s*([\\d.]+)/);
                    if (matchMonto) {
                        monto = matchMonto[1].replace(/\\./g, ''); // Remover puntos
                    }

                    if (monto) {
                        result.push({ id_nomina: id, monto: monto });
                    }
                });

                return result;
            }
        """)

        logger.info(f"Nóminas encontradas con montos: {datos}")
        return datos

    except Exception as e:
        logger.error(f"Error extrayendo nóminas con montos: {e}")
        return []


async def obtener_ids_nominas_tabla(page, fecha_busqueda=None):
    """
    Lee la tabla de nóminas y extrae solo los IDs con fecha ingreso especificada.

    Args:
        page: Página Playwright
        fecha_busqueda: Fecha a buscar (default: hoy). Formato: datetime object

    Returns:
        Lista de IDs de nóminas para esa fecha
    """
    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        fecha_str = fecha_busqueda.strftime("%d/%m/%Y")
        logger.info(f"Buscando nóminas con fecha ingreso: {fecha_str}")

        # Extraer datos directamente desde el DOM con JavaScript
        datos = await page.evaluate(f"""
            () => {{
                const ids = [];
                const fechaBusqueda = '{fecha_str}';

                // Método 1: Buscar por los divs que contienen IDs con ng-click
                const divs = document.querySelectorAll('[ng-click*="agregarOperacionDetalle"]');
                console.log(`Divs encontrados: ${{divs.length}}`);

                divs.forEach((div) => {{
                    const id = div.textContent.trim();

                    // Validar que sea un ID (6-7 dígitos)
                    if (!id.match(/^\\d{{6,7}}$/)) return;

                    // Buscar hacia arriba en el DOM para encontrar la fila
                    let elemento = div;
                    let encontradoFecha = false;

                    // Subir hasta 10 niveles en el árbol del DOM
                    for (let i = 0; i < 10; i++) {{
                        elemento = elemento.parentElement;
                        if (!elemento) break;

                        if (elemento.textContent.includes(fechaBusqueda)) {{
                            encontradoFecha = true;
                            break;
                        }}
                    }}

                    if (encontradoFecha) {{
                        ids.push(id);
                        console.log(`Fecha encontrada para ID: ${{id}}`);
                    }}
                }});

                console.log(`Total IDs de HOY: ${{ids.length}}`);
                return ids;
            }}
        """)

        logger.info(f"Nóminas de HOY encontradas: {datos}")
        return datos

    except Exception as e:
        logger.error(f"Error extrayendo IDs de tabla: {e}")
        return []


async def paso_2_descargar_nomina_por_id(page, id_nomina, fecha_busqueda=None):
    """
    Descarga PDF de nómina específica por su ID desde el menú de acciones.

    Args:
        page: Página Playwright
        id_nomina: ID de la nómina a descargar (ej: 1965892)
        fecha_busqueda: Fecha para nombrar archivo

    Returns:
        Ruta del PDF descargado
    """
    logger.info(f"PASO 2: Descargando PDF de nómina ID {id_nomina}...")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Buscar la fila con el ID específico y hacer click en dropdown
        dropdown_clicked = await page.evaluate(f"""
            () => {{
                // Buscar los divs que contienen los IDs con ng-click
                const divs = document.querySelectorAll('[ng-click*="agregarOperacionDetalle"]');
                for (let div of divs) {{
                    // Si este div contiene el ID que buscamos
                    if (div.textContent.trim() === '{id_nomina}') {{
                        // Subir al contenedor de la fila (div.rowspan)
                        let fila = div.closest('[ng-repeat*="transacciones"]') ||
                                   div.closest('.rowspan') ||
                                   div.closest('div[ng-repeat]');

                        if (fila) {{
                            // Encontrar el botón dropdown en esta fila
                            const actionBtn = fila.querySelector('button.dropdown');
                            if (actionBtn) {{
                                actionBtn.click();
                                return 'clicked';
                            }}
                        }}
                    }}
                }}
                return 'not found';
            }}
        """)
        logger.info(f"Dropdown click resultado: {dropdown_clicked}")
        await asyncio.sleep(2)  # Esperar a que se abra el dropdown completamente

        # Click en "Descarga PDF" dentro del dropdown abierto
        try:
            logger.info(f"Esperando descarga para nómina {id_nomina}...")
            async with page.expect_download() as download_info:
                # Usar JavaScript para clickear el botón dentro del dropdown abierto
                pdf_clicked = await page.evaluate("""
                    () => {
                        // Buscar el elemento <a> con "Descarga PDF" dentro del dropdown abierto
                        const links = document.querySelectorAll('a[ng-click*="getDescargaNominaOperacionPdf"]');
                        for (let link of links) {
                            // Verificar que el link esté visible (no está en display:none)
                            if (link.offsetParent !== null) {
                                link.click();
                                return 'clicked visible link';
                            }
                        }
                        return 'no visible link found';
                    }
                """)
                logger.info(f"PDF click resultado: {pdf_clicked}")
                download = await download_info.value
                logger.info(f"Descarga obtenida: {download}")
        except Exception as e:
            logger.error(f"Error esperando/obteniendo descarga: {e}")
            raise

        fecha_str = fecha_busqueda.strftime("%Y%m%d")
        nomina_path = NOMINAS_PATH / f"nomina_{fecha_str}_{id_nomina}.pdf"

        # Asegurar que el directorio existe
        NOMINAS_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(f"Directorio: {NOMINAS_PATH}, existe: {NOMINAS_PATH.exists()}")

        try:
            logger.info(f"Intentando guardar en: {nomina_path}")
            await download.save_as(str(nomina_path))
            logger.info(f"✓ Save_as completó sin errores")
            import time
            await asyncio.sleep(1)  # Dar tiempo a que se escriba el archivo
            exists = nomina_path.exists()
            logger.info(f"Archivo existe después de save_as: {exists}")
        except PermissionError:
            nomina_path = TEMP_DOWNLOAD_PATH / f"nomina_{fecha_str}_{id_nomina}_temp.pdf"
            await download.save_as(str(nomina_path))
            logger.warning(f"Archivo en uso, guardado como temporal: {nomina_path}")
        except Exception as e:
            logger.error(f"Error guardando PDF: {e}")
            return None

        # Verificar que el archivo se guardó
        for _ in range(5):  # Reintentar 5 veces
            if nomina_path.exists():
                logger.info(f"✓ PDF de nómina {id_nomina} descargado: {nomina_path}")
                # Cerrar dropdown al finalizar correctamente
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                except:
                    pass
                return nomina_path
            await asyncio.sleep(0.5)

        logger.error(f"PDF no se guardó en: {nomina_path}")
        return None

    except Exception as e:
        logger.error(f"Error descargando nómina {id_nomina}: {e}")
        # Cerrar dropdown incluso en caso de error
        try:
            await page.keyboard.press("Escape")
        except:
            pass
        return None


async def paso_2_descargar_nomina_por_monto(page, id_nomina, monto, fecha_busqueda=None):
    """
    Descarga PDF filtrando por monto específico (aisla esa nómina).

    Args:
        page: Página Playwright
        id_nomina: ID de la nómina
        monto: Monto exacto (string sin puntos: "73384191")
        fecha_busqueda: Fecha para nombrar archivo

    Returns:
        Ruta del PDF descargado
    """
    logger.info(f"Descargando nómina {id_nomina} por monto: ${monto}")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Filtrar por monto exacto en el rango "Desde" y "Hasta"
        monto_formateado = f"${monto[:2]}.{monto[2:5]}.{monto[5:]}" if len(monto) > 5 else f"${monto}"

        await page.evaluate(f"""
            () => {{
                const inputs = document.querySelectorAll('input[placeholder*="Desde"], input[placeholder*="Hasta"]');
                // Llenar "Desde" y "Hasta" con el mismo monto (para filtrar exacto)
                if (inputs.length >= 2) {{
                    inputs[0].value = '{monto_formateado}';
                    inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inputs[1].value = '{monto_formateado}';
                    inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}
        """)
        await asyncio.sleep(1)

        # Click en Filtrar
        try:
            await page.click("input[type='submit'][value='Filtrar']", timeout=5000)
            await asyncio.sleep(2)
        except:
            pass

        # Descargar usando la función por ID (ahora solo verá esta nómina)
        nomina_pdf_path = await paso_2_descargar_nomina_por_id(page, id_nomina, fecha_busqueda)

        # Limpiar filtro de monto
        try:
            await page.click("a:has-text('Limpiar Filtros')", timeout=5000)
            await asyncio.sleep(2)
        except:
            pass

        return nomina_pdf_path

    except Exception as e:
        logger.error(f"Error descargando nómina {id_nomina} por monto: {e}")
        return None


async def paso_2_descargar_nomina(page, fecha_busqueda=None, skip_count=0):
    """
    PASO 2: Descargar PDF de nómina (Estado de Firmas).

    Navega: Pagos > Pago Nómina > Consultar > Estado de Firmas
    Descarga el PDF de la primera nómina COMPLETADA no procesada.

    Args:
        skip_count: Número de nóminas a saltear (si la primera ya fue procesada)
    """
    logger.info(f"PASO 2: Descargando PDF de nómina (Estado de Firmas)... [skip={skip_count}]")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Click en "Pagos" del menú superior
        logger.info("Navegando a menú Pagos...")

        # Usar XPath para buscar el link "Pagos" EXACTO en el menú superior
        await page.click("xpath=(//nav//a[normalize-space()='Pagos'] | //*[@role='tablist']//a[normalize-space()='Pagos'])[1]", timeout=10000)
        logger.info("✓ Click en menú 'Pagos'")

        await asyncio.sleep(3)

        # Paso 2a: Intentar click en "Ingresar" si existe (opcional)
        logger.info("Buscando botón 'Ingresar'...")
        await asyncio.sleep(1)

        ingreso_necesario = await page.evaluate("""
            (function() {
                const allAnchors = document.querySelectorAll('a');
                for (let i = 0; i < allAnchors.length; i++) {
                    const link = allAnchors[i];
                    const text = link.textContent.trim();
                    if (text === 'Ingresar') {
                        return true;
                    }
                }
                return false;
            })()
        """)

        if ingreso_necesario:
            logger.info("Encontrado 'Ingresar', clickeando...")
            await page.evaluate("""
                (function() {
                    const allAnchors = document.querySelectorAll('a');
                    for (let i = 0; i < allAnchors.length; i++) {
                        const link = allAnchors[i];
                        if (link.textContent.trim() === 'Ingresar') {
                            link.scrollIntoView({behavior: 'smooth', block: 'center'});
                            link.click();
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            logger.info("✓ Click en 'Ingresar' exitoso")
            await asyncio.sleep(3)
        else:
            logger.info("ℹ No hay botón 'Ingresar', continuando a 'Consultar' directamente")

        # Paso 2b: Click en "Consultar" para ver la tabla de nóminas
        logger.info("Clickeando en 'Consultar'...")
        await asyncio.sleep(1)

        consultar_exitoso = await page.evaluate("""
            (function() {
                const allAnchors = document.querySelectorAll('a');
                for (let i = 0; i < allAnchors.length; i++) {
                    const link = allAnchors[i];
                    const text = link.textContent.trim();
                    if (text === 'Consultar') {
                        link.scrollIntoView({behavior: 'smooth', block: 'center'});
                        link.click();
                        return true;
                    }
                }
                return false;
            })()
        """)

        if consultar_exitoso:
            logger.info("✓ Click en 'Consultar' exitoso")
        else:
            logger.error("✗ No se pudo clickear 'Consultar'")
            raise Exception("No se pudo hacer click en botón 'Consultar'")

        await asyncio.sleep(3)

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


async def paso_2_descargar_nomina_por_id_excel(page, id_nomina, fecha_busqueda=None):
    """
    Descarga EXCEL de nómina específica por su ID (fallback cuando PDF está vacío).

    Args:
        page: Página Playwright
        id_nomina: ID de la nómina a descargar (ej: 1965892)
        fecha_busqueda: Fecha para nombrar archivo

    Returns:
        Ruta del Excel descargado
    """
    logger.info(f"PASO 2: Descargando EXCEL de nómina ID {id_nomina}...")

    try:
        if fecha_busqueda is None:
            fecha_busqueda = datetime.now()

        # Buscar la fila con el ID específico y hacer click en dropdown
        await page.evaluate(f"""
            () => {{
                const divs = document.querySelectorAll('[ng-click*="agregarOperacionDetalle"]');
                for (let div of divs) {{
                    if (div.textContent.trim() === '{id_nomina}') {{
                        let fila = div.closest('[ng-repeat*="transacciones"]') ||
                                   div.closest('.rowspan') ||
                                   div.closest('div[ng-repeat]');

                        if (fila) {{
                            const actionBtn = fila.querySelector('button.dropdown');
                            if (actionBtn) {{
                                actionBtn.click();
                                return 'clicked';
                            }}
                        }}
                    }}
                }}
                return 'not found';
            }}
        """)
        await asyncio.sleep(2)

        # Click en "Descarga Excel" dentro del dropdown abierto
        try:
            logger.info(f"Esperando descarga EXCEL para nómina {id_nomina}...")
            async with page.expect_download() as download_info:
                excel_clicked = await page.evaluate("""
                    () => {
                        // Intentar primero por ng-click con Excel
                        let links = document.querySelectorAll('a[ng-click*="getDescargaNominaOperacionExcel"]');
                        for (let link of links) {
                            if (link.offsetParent !== null) {
                                link.click();
                                return 'clicked by ng-click Excel';
                            }
                        }

                        // Fallback: buscar por texto "Excel" (case-insensitive)
                        links = document.querySelectorAll('a, span');
                        for (let link of links) {
                            const text = link.textContent.toLowerCase();
                            if ((text.includes('excel') || text.includes('descarga')) &&
                                link.textContent.toLowerCase().includes('excel') &&
                                link.offsetParent !== null) {
                                // Si es span, buscar el link padre
                                let clickTarget = link.tagName === 'A' ? link : link.closest('a');
                                if (clickTarget) {
                                    clickTarget.click();
                                    return 'clicked by text Excel';
                                }
                            }
                        }

                        return 'no Excel link found';
                    }
                """)
                logger.info(f"EXCEL click resultado: {excel_clicked}")
                download = await download_info.value
                logger.info(f"Descarga EXCEL obtenida: {download}")
        except Exception as e:
            logger.error(f"Error esperando/obteniendo descarga EXCEL: {e}")
            raise

        fecha_str = fecha_busqueda.strftime("%Y%m%d")
        excel_path = NOMINAS_PATH / f"nomina_{fecha_str}_{id_nomina}.xlsx"

        NOMINAS_PATH.mkdir(parents=True, exist_ok=True)

        try:
            await download.save_as(str(excel_path))
            logger.info(f"✓ Save_as completó sin errores")
            await asyncio.sleep(1)
        except PermissionError:
            excel_path = TEMP_DOWNLOAD_PATH / f"nomina_{fecha_str}_{id_nomina}_temp.xlsx"
            await download.save_as(str(excel_path))
            logger.warning(f"Archivo en uso, guardado como temporal: {excel_path}")
        except Exception as e:
            logger.error(f"Error guardando EXCEL: {e}")
            return None

        # Verificar que el archivo se guardó
        for _ in range(5):
            if excel_path.exists():
                logger.info(f"✓ EXCEL de nómina {id_nomina} descargado: {excel_path}")
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                except:
                    pass
                return excel_path
            await asyncio.sleep(0.5)

        logger.error(f"EXCEL no se guardó en: {excel_path}")
        return None

    except Exception as e:
        logger.error(f"Error descargando EXCEL de nómina {id_nomina}: {e}")
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except:
            pass
        return None
