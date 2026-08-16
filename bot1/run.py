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
import os
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

from config import (
    MODO_DRY_RUN, LOG_PATH, TEMP_DOWNLOAD_PATH,
    DRIVE_FOLDER_ID_CARTOLAS, DRIVE_FOLDER_ID_COMPROBANTES, DRIVE_FOLDER_ID_NOMINAS, BANCO_NOMBRE_CARPETA
)
from drive_utils import get_drive_service, get_carpeta_destino, upload_file
from pdf_parser import extraer_ruts_nomina
from procesos.login import paso_0_login
from procesos.descargar_cartola import paso_1_descargar_cartola
from procesos.procesar_cartola import paso_1_5_procesar_cartola
from procesos.descargar_nomina import paso_2_descargar_nomina, obtener_ids_nominas_tabla, paso_2_descargar_nomina_por_id, obtener_nominas_con_montos, paso_2_descargar_nomina_por_monto
from procesos.descargar_comprobantes import paso_3_descargar_todos_comprobantes
from pdf_parser import extraer_metadatos_nomina, extraer_ruts_nomina
from supabase_client import verificar_nomina, insertar_nomina, actualizar_nomina_estado, obtener_nominas_parciales

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
            # ========== ETAPA 0: Procesar nóminas PARCIALES de cualquier fecha ==========
            logger.info("=" * 80)
            logger.info("ETAPA 0: Verificando nóminas parciales pendientes...")
            logger.info("=" * 80)
            nominas_parciales = obtener_nominas_parciales()
            if nominas_parciales:
                logger.info(f"Encontradas {len(nominas_parciales)} nóminas parciales:")
                for nom in nominas_parciales:
                    logger.info(f"  - ID: {nom['id_nomina']}, Fecha carga: {nom['fecha_carga']}, Fecha pago: {nom['fecha_pago']}, Estado: {nom['estado']}")
            else:
                logger.info("No hay nóminas parciales pendientes")
            logger.info("=" * 80)
            # Fin ETAPA 0 - Las parciales se procesarán dentro del navegador después
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

                # ========== PASO 1.5: Procesar cartola (evitar duplicados) ==========
                filas_nuevas_cartola = []
                if cartola_path:
                    logger.info("Procesando cartola para evitar duplicados...")
                    filas_nuevas_cartola = await paso_1_5_procesar_cartola(cartola_path)
                    logger.info(f"Se encontraron {len(filas_nuevas_cartola)} filas nuevas en cartola")

                # ========== PASO 1.6: Subir cartola a Drive ==========
                if cartola_path and filas_nuevas_cartola:
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
                    # Borrar archivo local después de subir
                    try:
                        os.remove(str(cartola_path))
                        logger.info(f"✓ Archivo local eliminado: {cartola_path}")
                    except Exception as e:
                        logger.warning(f"No se pudo borrar archivo local: {e}")
                else:
                    logger.info("⚠ No hay cartola para subir (sin movimientos del día)")

                # ========== ETAPA 1: Procesar nóminas PARCIALES ==========
                # Filtro de optimización: solo procesar nóminas cuya fecha_pago == fecha_hoy
                nominas_parciales_filtradas = []
                for nom in nominas_parciales:
                    fecha_pago = datetime.strptime(nom['fecha_pago'], "%Y-%m-%d").date() if isinstance(nom['fecha_pago'], str) else nom['fecha_pago']
                    if fecha_pago == self.fecha_hoy.date():
                        nominas_parciales_filtradas.append(nom)

                if nominas_parciales_filtradas:
                    logger.info("=" * 80)
                    logger.info("ETAPA 1: Procesando nóminas parciales...")
                    logger.info("=" * 80)

                    ids_procesados_etapa1 = set()
                    logger.info(f"ETAPA 1: Iterando sobre {len(nominas_parciales_filtradas)} nóminas parciales del día")

                    for nom_parcial in nominas_parciales_filtradas:
                        id_nomina_parcial = nom_parcial['id_nomina']
                        logger.info(f"ETAPA 1: Procesando ID {id_nomina_parcial}")
                        fecha_carga_str = nom_parcial['fecha_carga']  # String: "2026-08-07"
                        fecha_pago_parcial = datetime.strptime(nom_parcial['fecha_pago'], "%Y-%m-%d").date() if isinstance(nom_parcial['fecha_pago'], str) else nom_parcial['fecha_pago']

                        logger.info(f"\n--- Procesando parcial: {id_nomina_parcial} (carga: {fecha_carga_str}, pago: {fecha_pago_parcial}) ---")

                        try:
                            # La nómina aparece en la tabla del banco el día SIGUIENTE a su carga
                            # No usar fecha_pago, usar fecha_carga + 1 día
                            fecha_carga_obj = datetime.strptime(str(fecha_carga_str), "%Y-%m-%d")
                            fecha_busqueda_tabla = fecha_carga_obj + timedelta(days=1)
                            fecha_pago_obj = datetime.strptime(str(fecha_pago_parcial), "%Y-%m-%d")

                            logger.info(f"Buscando en tabla con fecha: {fecha_busqueda_tabla.strftime('%d/%m/%Y')} (carga+1), fecha_pago real: {fecha_pago_obj.strftime('%d/%m/%Y')}")

                            # Navegar a Pagos > Consultar para filtrar por fecha_carga de esta nómina
                            await self.page.click("nav a:has-text('Pagos'), [role='tablist'] a:has-text('Pagos')", timeout=10000)
                            await asyncio.sleep(2)

                            await self.page.evaluate("""
                                (function() {
                                    const allAnchors = document.querySelectorAll('a');
                                    for (let i = 0; i < allAnchors.length; i++) {
                                        const link = allAnchors[i];
                                        if (!link.textContent.includes('Consultar')) continue;
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

                            # Abrir buscador y filtrar por fecha_carga+1 de esta nómina
                            try:
                                await self.page.click("a[ng-click*='openFilters']", timeout=5000)
                                await asyncio.sleep(1)
                            except:
                                pass

                            fecha_busqueda_str_fmt = fecha_busqueda_tabla.strftime("%d/%m/%Y")
                            await self.page.evaluate(f"""
                                () => {{
                                    const inputs = document.querySelectorAll('input.md-datepicker-input');
                                    if (inputs.length >= 1) {{
                                        inputs[0].value = '{fecha_busqueda_str_fmt}';
                                        inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    }}
                                    if (inputs.length >= 2) {{
                                        inputs[1].value = '{fecha_busqueda_str_fmt}';
                                        inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    }}
                                }}
                            """)
                            await asyncio.sleep(0.5)

                            # Click en Filtrar
                            try:
                                await self.page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                                await asyncio.sleep(2)
                            except:
                                logger.warning(f"No se pudo hacer click en Filtrar para nómina parcial")

                            # Intentar buscar esta nómina en la tabla filtrada
                            try:
                                await self.page.wait_for_function(
                                    "() => document.querySelector('.table-flex') && document.querySelectorAll('[ng-click*=\"agregarOperacionDetalle\"]').length > 0",
                                    timeout=5000
                                )
                            except:
                                logger.warning(f"ETAPA 1: SKIP - tabla no cargó para {fecha_pago_str_fmt}")
                                continue

                            # Obtener IDs Y MONTOS de la tabla filtrada para esta fecha
                            nominas_fecha = await obtener_nominas_con_montos(self.page, fecha_pago_obj)
                            ids_fecha = [nom['id_nomina'] for nom in nominas_fecha]

                            # Encontrar el monto de esta nómina (si existe en tabla)
                            monto = None
                            for nom in nominas_fecha:
                                if nom['id_nomina'] == id_nomina_parcial:
                                    monto = nom['monto']
                                    break

                            # Si la nómina NO está en tabla (porque fecha_pago es antigua)
                            # Intenta descargar por ID directamente
                            if id_nomina_parcial not in ids_fecha:
                                logger.info(f"ETAPA 1: Nómina {id_nomina_parcial} no en tabla {fecha_pago_str_fmt}, intentando descargar por ID directo")
                                # Saltear filtrado por monto e ir directo a descargar
                                monto = None
                            else:
                                # Filtrar por monto (regla: SIEMPRE filtrar por monto)
                                if monto:
                                    monto_hasta = str(int(monto) + 1)
                                    logger.info(f"ETAPA 1: Filtrando por monto ${monto} a ${monto_hasta} para {id_nomina_parcial}")

                                    await self.page.evaluate(f"""
                                        () => {{
                                            const inputDesde = document.querySelector('input[name="montoInicio"]');
                                            const inputHasta = document.querySelector('input[name="montoFinal"]');

                                            if (inputDesde && inputHasta) {{
                                                inputDesde.value = '{monto}';
                                                inputDesde.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                                inputDesde.dispatchEvent(new Event('change', {{ bubbles: true }}));

                                                inputHasta.value = '{monto_hasta}';
                                                inputHasta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                                inputHasta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            }}
                                        }}
                                    """)
                                    await asyncio.sleep(1)

                                    try:
                                        await self.page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                                        await asyncio.sleep(2)
                                    except:
                                        pass

                            # Descargar el PDF de esta nómina
                            logger.info(f"ETAPA 1: Descargando PDF para {id_nomina_parcial}")
                            nomina_pdf_path = await paso_2_descargar_nomina_por_id(self.page, id_nomina_parcial, fecha_pago_obj)
                            logger.info(f"ETAPA 1: Descarga completada, path={nomina_pdf_path}")

                            # Limpiar filtro de monto después de descargar
                            if monto:
                                try:
                                    await self.page.click("a:has-text('Limpiar Filtros')", timeout=5000)
                                    await asyncio.sleep(2)
                                    logger.info(f"ETAPA 1: Filtro de monto limpiado")
                                except:
                                    pass

                            if not nomina_pdf_path:
                                logger.warning(f"ETAPA 1: SKIP - descarga falló para {id_nomina_parcial}")
                                continue

                            # Reextraer metadatos (el estado podría haber cambiado)
                            try:
                                metadatos_nuevos = extraer_metadatos_nomina(nomina_pdf_path)
                                id_nom_extraido = metadatos_nuevos['id_nomina']
                                estado_nuevo = metadatos_nuevos.get('estado', '').lower()
                                fecha_pago_nueva = metadatos_nuevos['fecha_pago']

                                logger.info(f"Metadatos reextraídos: ID={id_nom_extraido}, Estado={estado_nuevo}, Fecha pago={fecha_pago_nueva}")

                                # Validar estado - detectar anulaciones
                                if "anulac" in estado_nuevo.lower():
                                    logger.info(f"ETAPA 1: Nómina ANULADA ({estado_nuevo}), marcar como anulada")
                                    actualizar_nomina_estado(id_nom_extraido, 'anulada')
                                    continue

                                # Validar estado - detectar pendiente de autorización
                                if "pendiente" in estado_nuevo.lower() or "autorizac" in estado_nuevo.lower():
                                    logger.info(f"ETAPA 1: Nómina pendiente de autorización ({estado_nuevo}), reintentar después")
                                    actualizar_nomina_estado(id_nom_extraido, 'pendiente')
                                    continue

                                # Validar estado
                                if "completada" not in estado_nuevo:
                                    logger.info(f"ETAPA 1: SKIP - no completada ({estado_nuevo})")
                                    continue

                                # Validar fecha_pago
                                if fecha_pago_nueva > self.fecha_hoy.date():
                                    logger.info(f"ETAPA 1: SKIP - fecha_pago futura ({fecha_pago_nueva})")
                                    continue

                                # AHORA SÍ: está completada y fecha_pago es válida → procesar completo
                                logger.info(f"Nómina parcial {id_nomina_parcial} AHORA está lista para completar!")

                                # Subir nómina a Drive
                                TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                                folder_id_nominas = get_carpeta_destino(
                                    self.drive_service,
                                    DRIVE_FOLDER_ID_NOMINAS,
                                    BANCO_NOMBRE_CARPETA,
                                    fecha_pago_nueva,
                                    TEAM_DRIVE_ID
                                )
                                try:
                                    file_name_nomina = f"nomina_{BANCO_NOMBRE_CARPETA}_{fecha_pago_nueva.strftime('%Y%m%d')}_{id_nom_extraido}.pdf"
                                    upload_file(self.drive_service, nomina_pdf_path, folder_id_nominas, file_name_nomina)
                                    logger.info(f"✓ Nómina {id_nom_extraido} subida a Drive: {folder_id_nominas}")
                                except Exception as e:
                                    logger.error(f"Error subiendo nómina a Drive: {e}")

                                # Extraer RUTs
                                ruts_unicos = extraer_ruts_nomina(nomina_pdf_path)
                                logger.info(f"Se encontraron {len(ruts_unicos)} RUTs únicos")

                                # Descargar comprobantes (con deduplicación en Drive)
                                if ruts_unicos:
                                    TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                                    folder_id_comprobantes = get_carpeta_destino(
                                        self.drive_service,
                                        DRIVE_FOLDER_ID_COMPROBANTES,
                                        BANCO_NOMBRE_CARPETA,
                                        self.fecha_hoy,
                                        TEAM_DRIVE_ID
                                    )

                                    comprobantes = await paso_3_descargar_todos_comprobantes(
                                        self.page, ruts_unicos, fecha_pago_nueva,
                                        drive_service=self.drive_service,
                                        folder_id_comprobantes=folder_id_comprobantes,
                                        paso_0_login_fn=paso_0_login,
                                        browser=self.browser
                                    )

                                    # Subir a Drive
                                    if comprobantes:
                                        subidos = 0
                                        for rut, comprobante_path in comprobantes:
                                            if comprobante_path is None:
                                                logger.info(f"✓ Comprobante para RUT {rut} ya estaba en Drive")
                                                subidos += 1
                                                continue

                                            try:
                                                rut_normalizado = rut.replace(".", "").replace("-", "")
                                                file_name = f"comprobante_{BANCO_NOMBRE_CARPETA}_{self.fecha_hoy.strftime('%Y%m%d')}_{rut_normalizado}.pdf"
                                                upload_file(self.drive_service, comprobante_path, folder_id_comprobantes, file_name)
                                                logger.info(f"Comprobante subido para RUT {rut}")
                                                try:
                                                    os.remove(str(comprobante_path))
                                                except:
                                                    pass
                                                subidos += 1
                                            except Exception as e:
                                                logger.error(f"Error subiendo comprobante para RUT {rut}: {e}")
                                                continue

                                        # Marcar como completo si todos se procesaron
                                        if subidos == len(comprobantes):
                                            actualizar_nomina_estado(id_nom_extraido, 'completo', ruta_drive=folder_id_comprobantes)
                                            logger.info(f"✓ Nómina parcial {id_nomina_parcial} COMPLETADA en Drive: {folder_id_comprobantes}")

                                # Limpiar PDF local
                                # COMENTADO PARA DEBUGGING: guardar nóminas localmente
                                # try:
                                #     os.remove(str(nomina_pdf_path))
                                # except:
                                #     pass

                            except Exception as e:
                                logger.error(f"Error procesando nómina parcial {id_nomina_parcial}: {e}")
                                # COMENTADO PARA DEBUGGING: guardar nóminas localmente
                                # try:
                                #     os.remove(str(nomina_pdf_path))
                                # except:
                                #     pass

                        except Exception as e:
                            logger.error(f"Error en flujo de nómina parcial {id_nomina_parcial}: {e}")

                        # Registrar que este ID fue INTENTADO procesar en ETAPA 1 (exitoso, saltado, o error)
                        # Esto previene que PASO 2 lo descargue de nuevo
                        logger.info(f"ETAPA 1: Registrando {id_nomina_parcial} (ya procesado/intentado)")
                        ids_procesados_etapa1.add(id_nomina_parcial)

                    logger.info("=" * 80)
                    logger.info(f"Fin ETAPA 1 - Procesadas: {ids_procesados_etapa1}")
                    logger.info("=" * 80)
                else:
                    ids_procesados_etapa1 = set()
                    if nominas_parciales:
                        logger.info("=" * 80)
                        logger.info(f"ETAPA 1: Hay {len(nominas_parciales)} nóminas parciales, pero NINGUNA del día {self.fecha_hoy.date()}")
                        logger.info("=" * 80)
                    else:
                        logger.info("=" * 80)
                        logger.info("ETAPA 1: No hay nóminas parciales pendientes")
                        logger.info("=" * 80)

                # ========== RESET: Limpiar filtros antes de PASO 2 ==========
                # Navegar de nuevo a Estado de Firmas para resetear el estado de la página
                # (Verificación 1: no deben quedar filtros de fecha antigua pegados)
                if nominas_parciales_filtradas:
                    logger.info("Reseteando estado de la página después de ETAPA 1...")
                    logger.info("⏸️  Pausa de 30s para recuperación del navegador después de procesar muchos comprobantes...")
                    await asyncio.sleep(30)  # Pausa larga para que navegador se recupere
                    try:
                        await self.page.click("nav a:has-text('Pagos'), [role='tablist'] a:has-text('Pagos')", timeout=10000)
                        await asyncio.sleep(2)
                    except:
                        pass

                # ========== REFRESH: Cerrar y abrir página nueva si hay nóminas parciales ==========
                if ids_procesados_etapa1:
                    logger.info("=" * 80)
                    logger.info("Cerrando página exhausta y abriendo nueva para PASO 2...")
                    logger.info("=" * 80)
                    await self.page.close()
                    self.page = await self.browser.new_page()
                    self.page.set_default_timeout(30000)
                    await paso_0_login(self.page)
                    logger.info("✓ Nueva sesión iniciada")

                # ========== PASO 2: Descargar nóminas no-procesadas de hoy ==========
                logger.info("PASO 2: Iniciando descarga de nóminas...")
                logger.info("⏸️  Pausa de 10s para resetear navegador después de descargas intensivas...")
                await asyncio.sleep(10)  # Pausa para que el navegador se recupere
                ids_nominas = []

                try:
                    # Navegar a Estado de Firmas (aumentado a 60s de timeout)
                    await self.page.wait_for_selector("nav a:has-text('Pagos')", timeout=60000)
                    await asyncio.sleep(1)
                    await self.page.click("nav a:has-text('Pagos')", timeout=10000)
                    await asyncio.sleep(3)

                    await self.page.evaluate("""
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

                    try:
                        await self.page.click("button:has-text('Estado de Firmas')", timeout=5000)
                        await asyncio.sleep(2)
                    except:
                        pass

                    # Abrir filtrador y buscar por fecha
                    try:
                        await self.page.click("a[ng-click*='openFilters']", timeout=5000)
                        await asyncio.sleep(1)
                    except:
                        pass

                    fecha_str = self.fecha_hoy.strftime("%d/%m/%Y")
                    await self.page.evaluate(f"""
                        () => {{
                            const inputs = document.querySelectorAll('input.md-datepicker-input');
                            if (inputs.length >= 1) {{
                                inputs[0].value = '{fecha_str}';
                                inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                                inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                            if (inputs.length >= 2) {{
                                inputs[1].value = '{fecha_str}';
                                inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                                inputs[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
                            }}
                        }}
                    """)
                    await asyncio.sleep(0.5)

                    try:
                        await self.page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                        await asyncio.sleep(2)
                    except:
                        pass

                    # Esperar tabla
                    try:
                        await self.page.wait_for_selector("button.dropdown", timeout=10000)
                        await asyncio.sleep(1)
                    except:
                        logger.info(f"No hay nóminas para {fecha_str}")
                        ids_nominas = []

                    # Obtener IDs y MONTOS
                    nominas_con_montos = await obtener_nominas_con_montos(self.page, self.fecha_hoy)
                    logger.info(f"Nóminas encontradas con montos: {nominas_con_montos}")

                    ids_nominas = [nom['id_nomina'] for nom in nominas_con_montos]
                    ids_nominas = sorted(ids_nominas, key=lambda x: int(x))
                    montos_por_id = {nom['id_nomina']: nom['monto'] for nom in nominas_con_montos}
                    logger.info(f"PASO 2: {len(ids_nominas)} nóminas para {fecha_str}: {ids_nominas}")
                    logger.info(f"Montos por ID: {montos_por_id}")

                    # Inspeccionar inputs disponibles
                    inputs_info = await self.page.evaluate("""
                        () => {
                            const inputs = document.querySelectorAll('input');
                            return Array.from(inputs)
                                .filter(inp => inp.offsetParent !== null)
                                .map(inp => ({
                                    type: inp.type,
                                    name: inp.name,
                                    id: inp.id,
                                    placeholder: inp.placeholder,
                                    value: inp.value
                                }))
                                .slice(0, 15);
                        }
                    """)
                    logger.info(f"Inputs visibles en página: {inputs_info}")

                except Exception as e:
                    logger.warning(f"Error navegando a PASO 2: {e}")
                    ids_nominas = []

                # Procesar cada nómina
                for idx, id_nom in enumerate(ids_nominas, 1):
                    # Saltear si ya fue procesada en ETAPA 1
                    if id_nom in ids_procesados_etapa1:
                        logger.info(f"[{idx}] Nómina {id_nom} ya procesada en ETAPA 1, saltando")
                        continue

                    nomina_pdf_path = None
                    ruts_unicos = []
                    monto = montos_por_id.get(id_nom)

                    try:
                        logger.info(f"\n[{idx}] Procesando nómina {id_nom}, Monto: ${monto}")

                        # Verificar si ya existe
                        nomina_en_bd = verificar_nomina(id_nom)
                        if nomina_en_bd and nomina_en_bd['estado'] == 'completo':
                            logger.info(f"Nómina {id_nom} ya completada en BD, saltando")
                            continue

                        # Filtrar por monto para aislar ESTA nómina
                        if monto:
                            monto_hasta = str(int(monto) + 1)
                            logger.info(f"Filtrando tabla por monto ${monto} a ${monto_hasta}...")

                            resultado = await self.page.evaluate(f"""
                                () => {{
                                    const inputDesde = document.querySelector('input[name="montoInicio"]');
                                    const inputHasta = document.querySelector('input[name="montoFinal"]');

                                    if (!inputDesde || !inputHasta) {{
                                        return 'inputs no encontrados';
                                    }}

                                    // Scroll a los inputs
                                    inputDesde.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

                                    // Llenar el input Desde
                                    inputDesde.value = '{monto}';
                                    inputDesde.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    inputDesde.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    inputDesde.dispatchEvent(new Event('keyup', {{ bubbles: true }}));

                                    // Llenar el input Hasta
                                    inputHasta.value = '{monto_hasta}';
                                    inputHasta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    inputHasta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    inputHasta.dispatchEvent(new Event('keyup', {{ bubbles: true }}));

                                    return 'inputs llenados';
                                }}
                            """)
                            logger.info(f"Resultado: {resultado}")
                            await asyncio.sleep(1)

                            # Click en Filtrar
                            try:
                                await self.page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                                await asyncio.sleep(2)
                                logger.info("Filtro de monto aplicado")
                            except Exception as e:
                                logger.warning(f"Error al filtrar por monto: {e}")

                        # Descargar PDF
                        nomina_pdf_path = await paso_2_descargar_nomina_por_id(self.page, id_nom, self.fecha_hoy)
                        if not nomina_pdf_path:
                            logger.warning(f"No se pudo descargar nómina {id_nom}")
                            continue

                        # Extraer metadatos
                        metadatos = extraer_metadatos_nomina(nomina_pdf_path)
                        id_nomina = metadatos['id_nomina']
                        fecha_pago = metadatos['fecha_pago']
                        estado = metadatos.get('estado', '').lower()

                        logger.info(f"✓ ID: {id_nomina}, Estado: {estado}, Pago: {fecha_pago}")

                        # Verificar estado - detectar anulaciones
                        if "anulac" in estado.lower():
                            logger.warning(f"Nómina ANULADA ({estado}), marcar como anulada e ignorar")
                            insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'anulada')
                            continue

                        # Verificar estado - detectar pendiente de autorización
                        if "pendiente" in estado.lower() or "autorizac" in estado.lower():
                            logger.info(f"Nómina pendiente de autorización ({estado}), reintentar después")
                            insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'pendiente')
                            continue

                        # Verificar que sea COMPLETADA
                        if "completada" not in estado:
                            logger.warning(f"Nómina no completada ({estado}), guardar como parcial")
                            insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')
                            continue

                        # Verificar que fecha_pago no sea futura
                        if fecha_pago > self.fecha_hoy.date():
                            logger.warning(f"Fecha pago futura ({fecha_pago}), guardar como parcial")
                            insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')
                            continue

                        # Subir nómina a Drive
                        TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                        folder_id_nominas = get_carpeta_destino(
                            self.drive_service,
                            DRIVE_FOLDER_ID_NOMINAS,
                            BANCO_NOMBRE_CARPETA,
                            fecha_pago,
                            TEAM_DRIVE_ID
                        )
                        try:
                            file_name_nomina = f"nomina_{BANCO_NOMBRE_CARPETA}_{fecha_pago.strftime('%Y%m%d')}_{id_nomina}.pdf"
                            upload_file(self.drive_service, nomina_pdf_path, folder_id_nominas, file_name_nomina)
                            logger.info(f"✓ Nómina {id_nomina} subida a Drive: {folder_id_nominas}")
                        except Exception as e:
                            logger.error(f"Error subiendo nómina a Drive: {e}")

                        # Extraer RUTs y guardar como parcial
                        ruts_unicos = extraer_ruts_nomina(nomina_pdf_path)
                        logger.info(f"Se encontraron {len(ruts_unicos)} RUTs únicos")
                        insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')

                    except Exception as e:
                        logger.error(f"Error procesando nómina {id_nom}: {e}")
                        continue

                    finally:
                        # Limpiar filtro de monto después de cada nómina
                        if monto and len(ids_nominas) > 1:
                            try:
                                await self.page.click("a:has-text('Limpiar Filtros')", timeout=5000)
                                await asyncio.sleep(2)
                                logger.info(f"Filtro de monto limpiado, listo para siguiente nómina")
                            except:
                                pass

                    # ========== PASO 3: Descargar comprobantes individuales ==========
                    if ruts_unicos:
                        logger.info(f"Descargando comprobantes para {len(ruts_unicos)} RUTs...")
                        try:
                            # Obtener folder_id primero para pasar a deduplicación
                            TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                            folder_id_comprobantes = get_carpeta_destino(
                                self.drive_service,
                                DRIVE_FOLDER_ID_COMPROBANTES,
                                BANCO_NOMBRE_CARPETA,
                                self.fecha_hoy,
                                TEAM_DRIVE_ID
                            )

                            comprobantes = await paso_3_descargar_todos_comprobantes(
                                self.page, ruts_unicos, fecha_pago,
                                drive_service=self.drive_service,
                                folder_id_comprobantes=folder_id_comprobantes,
                                paso_0_login_fn=paso_0_login,
                                browser=self.browser
                            )

                            # ========== PASO 3.5: Subir comprobantes a Drive ==========
                            if comprobantes:
                                logger.info("Subiendo comprobantes a Google Drive...")
                                subidos = 0
                                for rut, comprobante_path in comprobantes:
                                    # Si comprobante_path es None, significa que ya existía en Drive
                                    if comprobante_path is None:
                                        logger.info(f"✓ Comprobante para RUT {rut} ya estaba en Drive")
                                        subidos += 1
                                        continue

                                    try:
                                        rut_normalizado = rut.replace(".", "").replace("-", "")
                                        file_name = f"comprobante_{BANCO_NOMBRE_CARPETA}_{self.fecha_hoy.strftime('%Y%m%d')}_{rut_normalizado}.pdf"

                                        # Verificar que el archivo existe
                                        comprobante_path_obj = Path(str(comprobante_path))
                                        if not comprobante_path_obj.exists():
                                            logger.error(f"Archivo no existe: {comprobante_path}")
                                            continue

                                        logger.info(f"Subiendo comprobante: {file_name} ({comprobante_path_obj.stat().st_size} bytes)")
                                        upload_file(self.drive_service, comprobante_path, folder_id_comprobantes, file_name)
                                        logger.info(f"✓ Comprobante subido para RUT {rut}")

                                        # Borrar archivo local después de subir
                                        try:
                                            os.remove(str(comprobante_path))
                                            logger.info(f"Archivo local eliminado: {comprobante_path}")
                                        except Exception as e:
                                            logger.warning(f"No se pudo borrar comprobante local: {e}")
                                        subidos += 1
                                    except Exception as e:
                                        logger.error(f"Error subiendo comprobante para RUT {rut}: {e}", exc_info=True)
                                        continue

                                # Marcar nómina como completada si todos los comprobantes se procesaron (nuevos o existentes)
                                if id_nomina and subidos == len(comprobantes):
                                    actualizar_nomina_estado(id_nomina, 'completo', ruta_drive=folder_id_comprobantes)
                                    logger.info(f"Nómina {id_nomina} marcada como completa en Drive: {folder_id_comprobantes}")
                            else:
                                # No se descargaron comprobantes - mantener como parcial para reintentar en próximo horario
                                logger.warning(f"No se descargaron comprobantes para nómina {id_nomina}, se mantiene como parcial")
                                if id_nomina:
                                    actualizar_nomina_estado(id_nomina, 'parcial', ruta_drive=folder_id_comprobantes)
                                    logger.info(f"Nómina {id_nomina} mantiene estado parcial (sin comprobantes aún)")
                        except Exception as e:
                            logger.warning(f"PASO 3 (Comprobantes) falló: {e}")
                            # Dejar en 'parcial' para reintentar en próxima corrida
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
    import sys
    fecha_testing = None

    # Aceptar fecha como argumento: python run.py 2026-08-07
    if len(sys.argv) > 1:
        fecha_str = sys.argv[1]
        try:
            fecha_testing = datetime.strptime(fecha_str, "%Y-%m-%d")
            logger.info(f"Usando fecha de testing: {fecha_testing.strftime('%Y-%m-%d')}")
        except ValueError:
            logger.error(f"Formato de fecha inválido. Usar: YYYY-MM-DD")
            sys.exit(1)

    asyncio.run(main(fecha_testing))
