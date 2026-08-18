#!/usr/bin/env python3
"""
Prefect Flow: Bot de descarga de cartolas y comprobantes - Banco Consorcio

Convierte la lógica de bot1/run.py en un Prefect flow con:
- Patrón dual de secretos (local .env + Prefect Blocks)
- Tareas modulares con @task
- Logging con get_run_logger()
- Ejecución en schedule con work pools
"""

import asyncio
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, List, Tuple

from dotenv import load_dotenv
from prefect import flow, task, get_run_logger
from prefect.blocks.system import Secret
from prefect.cache_policies import NO_CACHE
from prefect.utilities.asyncutils import asynccontextmanager


def _ensure_dependencies():
	"""Instala dependencias faltantes automáticamente en Prefect workers."""
	required_packages = {
		"pdfplumber": "pdfplumber",
		"playwright": "playwright",
		"google-api-python-client": "googleapiclient",
		"google-auth": "google.auth",
		"supabase": "supabase",
		"openpyxl": "openpyxl",
		"pandas": "pandas"
	}

	missing = []
	for pkg_name, import_name in required_packages.items():
		try:
			__import__(import_name.split(".")[0])
		except ImportError:
			missing.append(pkg_name)

	if missing:
		print(f"⚠ Instalando paquetes faltantes: {', '.join(missing)}")
		subprocess.check_call(
			[sys.executable, "-m", "pip", "install", "-q"] + missing,
			stderr=subprocess.STDOUT
		)


_ensure_dependencies()

# Cargar .env primero
load_dotenv()

# Agregar bot1 al path para importar sus módulos
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "bot1"))

from config import (
    MODO_DRY_RUN, LOG_PATH, TEMP_DOWNLOAD_PATH,
    DRIVE_FOLDER_ID_CARTOLAS, DRIVE_FOLDER_ID_COMPROBANTES, DRIVE_FOLDER_ID_NOMINAS,
    BANCO_NOMBRE_CARPETA, BANCO_URL_LOGIN, BANCO_URL_CUENTAS
)
from drive_utils import get_drive_service, get_carpeta_destino, upload_file
from pdf_parser import extraer_ruts_nomina, extraer_metadatos_nomina
from procesos.login import paso_0_login
from procesos.descargar_cartola import paso_1_descargar_cartola
from procesos.procesar_cartola import paso_1_5_procesar_cartola
from procesos.descargar_nomina import (
    paso_2_descargar_nomina_por_id, obtener_nominas_con_montos
)
from procesos.descargar_comprobantes import paso_3_descargar_todos_comprobantes
from supabase_client import (
    verificar_nomina, insertar_nomina, actualizar_nomina_estado, obtener_nominas_parciales
)


def get_secret(block_name: str, env_var: str) -> str:
    """
    Patrón dual de secretos: intenta Prefect Block primero, luego .env

    Args:
        block_name: Nombre del Prefect Secret Block (ej: "supabase-url")
        env_var: Variable de entorno como fallback (ej: "SUPABASE_URL")

    Returns:
        Valor del secreto

    Raises:
        ValueError: Si no encuentra el secreto en Prefect ni en .env
    """
    logger = get_run_logger()

    # Intentar Prefect Block primero
    try:
        secret_block = Secret.load(block_name)
        value = secret_block.get()
        logger.info(f"✓ Secreto cargado desde Prefect Block: {block_name}")
        return value
    except Exception as e:
        logger.debug(f"Prefect Block {block_name} no disponible: {e}")

    # Fallback a variable de entorno
    value = os.getenv(env_var)
    if value:
        logger.info(f"✓ Secreto cargado desde .env: {env_var}")
        return value

    raise ValueError(f"Secreto no encontrado: block={block_name}, env_var={env_var}")


@task(name="task_obtener_nominas_parciales")
def task_obtener_nominas_parciales() -> List[dict]:
    """ETAPA 0: Obtener nóminas parciales pendientes"""
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("ETAPA 0: Verificando nóminas parciales pendientes...")
    logger.info("=" * 80)

    nominas_parciales = obtener_nominas_parciales()
    if nominas_parciales:
        logger.info(f"Encontradas {len(nominas_parciales)} nóminas parciales:")
        for nom in nominas_parciales:
            logger.info(f"  - ID: {nom['id_nomina']}, Fecha carga: {nom['fecha_carga']}, "
                       f"Fecha pago: {nom['fecha_pago']}, Estado: {nom['estado']}")
    else:
        logger.info("No hay nóminas parciales pendientes")

    return nominas_parciales


@task(name="task_descargar_cartola_step", cache_policy=NO_CACHE)
async def task_descargar_cartola_step(page, fecha_hoy) -> Optional[Path]:
    """PASO 1: Descargar cartola"""
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("PASO 1: Descargando cartola...")
    logger.info("=" * 80)

    cartola_path = await paso_1_descargar_cartola(page, fecha_hoy)
    return cartola_path


@task(name="task_procesar_cartola_step")
async def task_procesar_cartola_step(cartola_path: Optional[Path]) -> List[dict]:
    """PASO 1.5: Procesar cartola para evitar duplicados"""
    logger = get_run_logger()

    if not cartola_path:
        logger.info("⚠ No hay cartola para procesar")
        return []

    logger.info("Procesando cartola para evitar duplicados...")
    filas_nuevas_cartola = await paso_1_5_procesar_cartola(cartola_path)
    logger.info(f"Se encontraron {len(filas_nuevas_cartola)} filas nuevas en cartola")

    return filas_nuevas_cartola


@task(name="task_subir_cartola_step")
def task_subir_cartola_step(cartola_path: Optional[Path], filas_nuevas: List[dict],
                           fecha_hoy, drive_service) -> bool:
    """PASO 1.6: Subir cartola a Google Drive"""
    logger = get_run_logger()

    if not cartola_path or not filas_nuevas:
        logger.info("⚠ No hay cartola para subir (sin movimientos del día)")
        return False

    try:
        logger.info("Subiendo cartola a Google Drive...")
        TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
        folder_id = get_carpeta_destino(
            drive_service,
            DRIVE_FOLDER_ID_CARTOLAS,
            BANCO_NOMBRE_CARPETA,
            fecha_hoy,
            TEAM_DRIVE_ID
        )
        file_name = f"cartola_{BANCO_NOMBRE_CARPETA}_{fecha_hoy.strftime('%Y%m%d')}.xlsx"
        upload_file(drive_service, cartola_path, folder_id, file_name)
        logger.info("✓ Cartola subida a Drive")

        # Borrar archivo local
        try:
            os.remove(str(cartola_path))
            logger.info(f"✓ Archivo local eliminado: {cartola_path}")
        except Exception as e:
            logger.warning(f"No se pudo borrar archivo local: {e}")

        return True
    except Exception as e:
        logger.error(f"Error subiendo cartola: {e}")
        return False


@task(name="task_procesar_etapa1", cache_policy=NO_CACHE)
async def task_procesar_etapa1(page, nominas_parciales: List[dict], fecha_hoy,
                              drive_service, browser) -> Set[str]:
    """
    ETAPA 1: Procesar nóminas PARCIALES
    Reintentar nóminas parciales con hasta 48 comprobantes posibles
    """
    logger = get_run_logger()

    if not nominas_parciales:
        return set()

    logger.info("=" * 80)
    logger.info("ETAPA 1: Procesando nóminas parciales...")
    logger.info("=" * 80)

    ids_procesados_etapa1 = set()
    logger.info(f"ETAPA 1: Iterando sobre {len(nominas_parciales)} nóminas parciales")

    for nom_parcial in nominas_parciales:
        id_nomina_parcial = nom_parcial['id_nomina']
        logger.info(f"ETAPA 1: Procesando ID {id_nomina_parcial}")
        fecha_carga_str = nom_parcial['fecha_carga']
        fecha_pago_parcial = datetime.strptime(
            nom_parcial['fecha_pago'], "%Y-%m-%d"
        ).date() if isinstance(nom_parcial['fecha_pago'], str) else nom_parcial['fecha_pago']

        try:
            fecha_carga_obj = datetime.strptime(fecha_carga_str, "%Y-%m-%d")

            # Navegar a Pagos > Consultar para filtrar por fecha_carga
            try:
                await page.click(
                    "nav a:has-text('Pagos'), [role='tablist'] a:has-text('Pagos')",
                    timeout=10000
                )
                await asyncio.sleep(2)
            except:
                logger.warning(f"No se pudo hacer click en Pagos")
                continue

            # Buscar "Pago nómina" > "Consultar"
            await page.evaluate("""
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

            # Abrir filtrador
            try:
                await page.click("a[ng-click*='openFilters']", timeout=5000)
                await asyncio.sleep(1)
            except:
                pass

            # Filtrar por fecha_carga
            fecha_carga_str_fmt = fecha_carga_obj.strftime("%d/%m/%Y")
            await page.evaluate(f"""
                () => {{
                    const inputs = document.querySelectorAll('input.md-datepicker-input');
                    if (inputs.length >= 1) {{
                        inputs[0].value = '{fecha_carga_str_fmt}';
                        inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                    if (inputs.length >= 2) {{
                        inputs[1].value = '{fecha_carga_str_fmt}';
                        inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}
            """)
            await asyncio.sleep(0.5)

            # Click Filtrar
            try:
                await page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                await asyncio.sleep(2)
            except:
                logger.warning(f"No se pudo hacer click en Filtrar")

            # Esperar tabla
            try:
                await page.wait_for_function(
                    "() => document.querySelector('.table-flex') && "
                    "document.querySelectorAll('[ng-click*=\"agregarOperacionDetalle\"]').length > 0",
                    timeout=5000
                )
            except:
                logger.warning(f"ETAPA 1: SKIP - tabla no cargó para {fecha_carga_str_fmt}")
                ids_procesados_etapa1.add(id_nomina_parcial)
                continue

            # Obtener nóminas con montos de tabla filtrada
            nominas_fecha = await obtener_nominas_con_montos(page, fecha_carga_obj)
            ids_fecha = [nom['id_nomina'] for nom in nominas_fecha]

            # Encontrar monto
            monto = None
            for nom in nominas_fecha:
                if nom['id_nomina'] == id_nomina_parcial:
                    monto = nom['monto']
                    break

            # Si no está en tabla, intentar descargar por ID directo
            if id_nomina_parcial not in ids_fecha:
                logger.info(
                    f"ETAPA 1: Nómina {id_nomina_parcial} no en tabla {fecha_carga_str_fmt}, "
                    "intentando descargar por ID directo"
                )
                monto = None
            else:
                # Filtrar por monto
                if monto:
                    monto_hasta = str(int(monto) + 1)
                    logger.info(
                        f"ETAPA 1: Filtrando por monto ${monto} a ${monto_hasta} para {id_nomina_parcial}"
                    )

                    await page.evaluate(f"""
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
                        await page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                        await asyncio.sleep(2)
                    except:
                        pass

            # Descargar PDF de nómina
            logger.info(f"ETAPA 1: Descargando PDF para {id_nomina_parcial}")
            nomina_pdf_path = await paso_2_descargar_nomina_por_id(page, id_nomina_parcial, fecha_carga_obj)
            logger.info(f"ETAPA 1: Descarga completada, path={nomina_pdf_path}")

            # Limpiar filtro de monto
            if monto:
                try:
                    await page.click("a:has-text('Limpiar Filtros')", timeout=5000)
                    await asyncio.sleep(2)
                    logger.info("ETAPA 1: Filtro de monto limpiado")
                except:
                    pass

            if not nomina_pdf_path:
                logger.warning(f"ETAPA 1: SKIP - descarga falló para {id_nomina_parcial}")
                ids_procesados_etapa1.add(id_nomina_parcial)
                continue

            # Reextraer metadatos
            try:
                metadatos_nuevos = extraer_metadatos_nomina(nomina_pdf_path)
                id_nom_extraido = metadatos_nuevos['id_nomina']
                estado_nuevo = metadatos_nuevos.get('estado', '').lower()
                fecha_pago_nueva = metadatos_nuevos['fecha_pago']

                logger.info(
                    f"Metadatos reextraídos: ID={id_nom_extraido}, Estado={estado_nuevo}, "
                    f"Fecha pago={fecha_pago_nueva}"
                )

                # Detectar anulaciones
                if "anulac" in estado_nuevo.lower():
                    logger.info(f"ETAPA 1: Nómina ANULADA ({estado_nuevo}), marcar como anulada")
                    actualizar_nomina_estado(id_nom_extraido, 'anulada')
                    ids_procesados_etapa1.add(id_nomina_parcial)
                    continue

                # Detectar pendiente de autorización
                if "pendiente" in estado_nuevo.lower() or "autorizac" in estado_nuevo.lower():
                    logger.info(
                        f"ETAPA 1: Nómina pendiente de autorización ({estado_nuevo}), "
                        "reintentar después"
                    )
                    actualizar_nomina_estado(id_nom_extraido, 'pendiente')
                    ids_procesados_etapa1.add(id_nomina_parcial)
                    continue

                # Validar estado completada
                if "completada" not in estado_nuevo:
                    logger.info(f"ETAPA 1: SKIP - no completada ({estado_nuevo})")
                    ids_procesados_etapa1.add(id_nomina_parcial)
                    continue

                # Validar fecha_pago
                if fecha_pago_nueva > fecha_hoy.date():
                    logger.info(f"ETAPA 1: SKIP - fecha_pago futura ({fecha_pago_nueva})")
                    ids_procesados_etapa1.add(id_nomina_parcial)
                    continue

                # Está lista: extraer RUTs y descargar comprobantes
                logger.info(f"Nómina parcial {id_nomina_parcial} AHORA está lista para completar!")

                ruts_unicos = extraer_ruts_nomina(nomina_pdf_path)
                logger.info(f"Se encontraron {len(ruts_unicos)} RUTs únicos")

                if ruts_unicos:
                    TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                    folder_id_comprobantes = get_carpeta_destino(
                        drive_service,
                        DRIVE_FOLDER_ID_COMPROBANTES,
                        BANCO_NOMBRE_CARPETA,
                        fecha_hoy,
                        TEAM_DRIVE_ID
                    )

                    comprobantes = await paso_3_descargar_todos_comprobantes(
                        page, ruts_unicos, fecha_pago_nueva,
                        drive_service=drive_service,
                        folder_id_comprobantes=folder_id_comprobantes,
                        paso_0_login_fn=paso_0_login,
                        browser=browser
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
                                file_name = f"comprobante_{BANCO_NOMBRE_CARPETA}_{fecha_hoy.strftime('%Y%m%d')}_{rut_normalizado}.pdf"
                                upload_file(drive_service, comprobante_path, folder_id_comprobantes, file_name)
                                logger.info(f"Comprobante subido para RUT {rut}")
                                try:
                                    os.remove(str(comprobante_path))
                                except:
                                    pass
                                subidos += 1
                            except Exception as e:
                                logger.error(f"Error subiendo comprobante para RUT {rut}: {e}")
                                continue

                        # Marcar como completo
                        if subidos == len(comprobantes):
                            actualizar_nomina_estado(id_nom_extraido, 'completo', ruta_drive=folder_id_comprobantes)
                            logger.info(
                                f"✓ Nómina parcial {id_nomina_parcial} COMPLETADA en Drive: "
                                f"{folder_id_comprobantes}"
                            )

            except Exception as e:
                logger.error(f"Error procesando nómina parcial {id_nomina_parcial}: {e}")

        except Exception as e:
            logger.error(f"Error en flujo de nómina parcial {id_nomina_parcial}: {e}")

        ids_procesados_etapa1.add(id_nomina_parcial)

    logger.info("=" * 80)
    logger.info(f"Fin ETAPA 1 - Procesadas: {ids_procesados_etapa1}")
    logger.info("=" * 80)

    return ids_procesados_etapa1


@task(name="task_procesar_paso2", cache_policy=NO_CACHE)
async def task_procesar_paso2(page, fecha_hoy, drive_service, browser,
                             ids_procesados_etapa1: Set[str]) -> List[Tuple[str, Optional[Path]]]:
    """
    PASO 2-3.5: Descargar nóminas nuevas del día y comprobantes
    """
    logger = get_run_logger()
    logger.info("=" * 80)
    logger.info("PASO 2: Iniciando descarga de nóminas...")
    logger.info("=" * 80)

    ids_nominas = []
    montos_por_id = {}

    try:
        # Navegar a Pagos > Pago nómina > Consultar > Estado de Firmas
        await page.wait_for_selector("nav a:has-text('Pagos')", timeout=60000)
        await asyncio.sleep(1)
        await page.click("nav a:has-text('Pagos')", timeout=10000)
        await asyncio.sleep(3)

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

        try:
            await page.click("button:has-text('Estado de Firmas')", timeout=5000)
            await asyncio.sleep(2)
        except:
            pass

        # Filtrar por fecha
        try:
            await page.click("a[ng-click*='openFilters']", timeout=5000)
            await asyncio.sleep(1)
        except:
            pass

        fecha_str = fecha_hoy.strftime("%d/%m/%Y")
        await page.evaluate(f"""
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
            await page.click("input[type='submit'][value='Filtrar']", timeout=5000)
            await asyncio.sleep(2)
        except:
            pass

        # Esperar tabla
        try:
            await page.wait_for_selector("button.dropdown", timeout=10000)
            await asyncio.sleep(1)
        except:
            logger.info(f"No hay nóminas para {fecha_str}")
            return []

        # Obtener IDs y montos
        nominas_con_montos = await obtener_nominas_con_montos(page, fecha_hoy)
        logger.info(f"Nóminas encontradas con montos: {nominas_con_montos}")

        ids_nominas = [nom['id_nomina'] for nom in nominas_con_montos]
        ids_nominas = sorted(ids_nominas, key=lambda x: int(x))
        montos_por_id = {nom['id_nomina']: nom['monto'] for nom in nominas_con_montos}

        logger.info(f"PASO 2: {len(ids_nominas)} nóminas para {fecha_str}: {ids_nominas}")
        logger.info(f"Montos por ID: {montos_por_id}")

    except Exception as e:
        logger.warning(f"Error navegando a PASO 2: {e}")

    # Procesar cada nómina
    resultados = []

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
                resultados.append((id_nom, None))
                continue

            # Filtrar por monto
            if monto and len(ids_nominas) > 1:
                monto_hasta = str(int(monto) + 1)
                logger.info(f"Filtrando tabla por monto ${monto} a ${monto_hasta}...")

                await page.evaluate(f"""
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
                    await page.click("input[type='submit'][value='Filtrar']", timeout=5000)
                    await asyncio.sleep(2)
                    logger.info("Filtro de monto aplicado")
                except Exception as e:
                    logger.warning(f"Error al filtrar por monto: {e}")

            # Descargar PDF
            nomina_pdf_path = await paso_2_descargar_nomina_por_id(page, id_nom, fecha_hoy)
            if not nomina_pdf_path:
                logger.warning(f"No se pudo descargar nómina {id_nom}")
                resultados.append((id_nom, None))
                continue

            # Extraer metadatos
            metadatos = extraer_metadatos_nomina(nomina_pdf_path)
            id_nomina = metadatos['id_nomina']
            fecha_pago = metadatos['fecha_pago']
            estado = metadatos.get('estado', '').lower()

            logger.info(f"✓ ID: {id_nomina}, Estado: {estado}, Pago: {fecha_pago}")

            # Validaciones
            if "anulac" in estado.lower():
                logger.warning(f"Nómina ANULADA ({estado}), marcar como anulada")
                insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'anulada')
                resultados.append((id_nom, None))
                continue

            if "pendiente" in estado.lower() or "autorizac" in estado.lower():
                logger.info(f"Nómina pendiente de autorización ({estado}), reintentar después")
                insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'pendiente')
                resultados.append((id_nom, None))
                continue

            if "completada" not in estado:
                logger.warning(f"Nómina no completada ({estado}), guardar como parcial")
                insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')
                resultados.append((id_nom, None))
                continue

            if fecha_pago > fecha_hoy.date():
                logger.warning(f"Fecha pago futura ({fecha_pago}), guardar como parcial")
                insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')
                resultados.append((id_nom, None))
                continue

            # Extraer RUTs
            ruts_unicos = extraer_ruts_nomina(nomina_pdf_path)
            logger.info(f"Se encontraron {len(ruts_unicos)} RUTs únicos")
            insertar_nomina(id_nomina, metadatos['fecha_carga'], fecha_pago, 'parcial')

            # PASO 3: Descargar comprobantes
            if ruts_unicos:
                logger.info(f"Descargando comprobantes para {len(ruts_unicos)} RUTs...")
                try:
                    TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"
                    folder_id_comprobantes = get_carpeta_destino(
                        drive_service,
                        DRIVE_FOLDER_ID_COMPROBANTES,
                        BANCO_NOMBRE_CARPETA,
                        fecha_hoy,
                        TEAM_DRIVE_ID
                    )

                    comprobantes = await paso_3_descargar_todos_comprobantes(
                        page, ruts_unicos, fecha_pago,
                        drive_service=drive_service,
                        folder_id_comprobantes=folder_id_comprobantes,
                        paso_0_login_fn=paso_0_login,
                        browser=browser
                    )

                    # PASO 3.5: Subir comprobantes a Drive
                    if comprobantes:
                        logger.info("Subiendo comprobantes a Google Drive...")
                        subidos = 0
                        for rut, comprobante_path in comprobantes:
                            if comprobante_path is None:
                                logger.info(f"✓ Comprobante para RUT {rut} ya estaba en Drive")
                                subidos += 1
                                continue

                            try:
                                rut_normalizado = rut.replace(".", "").replace("-", "")
                                file_name = f"comprobante_{BANCO_NOMBRE_CARPETA}_{fecha_hoy.strftime('%Y%m%d')}_{rut_normalizado}.pdf"

                                comprobante_path_obj = Path(str(comprobante_path))
                                if not comprobante_path_obj.exists():
                                    logger.error(f"Archivo no existe: {comprobante_path}")
                                    continue

                                logger.info(f"Subiendo: {file_name} ({comprobante_path_obj.stat().st_size} bytes)")
                                upload_file(drive_service, comprobante_path, folder_id_comprobantes, file_name)
                                logger.info(f"✓ Comprobante subido para RUT {rut}")

                                try:
                                    os.remove(str(comprobante_path))
                                    logger.info(f"Archivo local eliminado: {comprobante_path}")
                                except:
                                    pass
                                subidos += 1
                            except Exception as e:
                                logger.error(f"Error subiendo comprobante para RUT {rut}: {e}")
                                continue

                        # Marcar como completado
                        if id_nomina and subidos == len(comprobantes):
                            actualizar_nomina_estado(id_nomina, 'completo', ruta_drive=folder_id_comprobantes)
                            logger.info(
                                f"Nómina {id_nomina} marcada como completa en Drive: {folder_id_comprobantes}"
                            )
                            resultados.append((id_nom, nomina_pdf_path))
                    else:
                        logger.warning("No se descargaron comprobantes")
                        resultados.append((id_nom, nomina_pdf_path))
                except Exception as e:
                    logger.warning(f"PASO 3 (Comprobantes) falló: {e}")
                    resultados.append((id_nom, nomina_pdf_path))
            else:
                logger.warning("No hay RUTs para descargar comprobantes")
                resultados.append((id_nom, nomina_pdf_path))

        except Exception as e:
            logger.error(f"Error procesando nómina {id_nom}: {e}")
            resultados.append((id_nom, None))

        finally:
            # Limpiar filtro de monto después de cada nómina
            if monto and len(ids_nominas) > 1:
                try:
                    await page.click("a:has-text('Limpiar Filtros')", timeout=5000)
                    await asyncio.sleep(2)
                    logger.info("Filtro de monto limpiado")
                except:
                    pass

    return resultados


@flow(name="valle-frio-bot-flow", description="Bot de cartolas y comprobantes - Banco Consorcio", version="1.0.0")
async def valle_frio_bot_flow(fecha_testing: Optional[str] = None):
    """
    Prefect Flow principal: Valle Frío Bot

    Pasos:
    - ETAPA 0: Obtener nóminas parciales pendientes
    - PASO 0: Login al banco
    - PASO 1-1.6: Descargar/procesar cartola
    - ETAPA 1: Reintentar nóminas parciales (hasta 48 comprobantes)
    - PASO 2-2.6: Nóminas nuevas del día
    - PASO 3-3.5: Comprobantes + Drive

    Args:
        fecha_testing: Fecha para testing (default: hoy). Formato: YYYY-MM-DD
    """
    logger = get_run_logger()

    logger.info("=" * 80)
    logger.info("INICIANDO BOT CONSORCIO (PREFECT FLOW)")
    logger.info("=" * 80)

    # Determinar fecha
    if fecha_testing:
        try:
            fecha_hoy = datetime.strptime(fecha_testing, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Formato de fecha inválido: {fecha_testing}. Usar YYYY-MM-DD")
    else:
        fecha_hoy = datetime.now()

    logger.info(f"Fecha: {fecha_hoy.strftime('%Y-%m-%d')}")
    logger.info(f"Modo: {'DRY RUN' if MODO_DRY_RUN else 'PRODUCCIÓN'}")

    # ETAPA 0
    nominas_parciales = task_obtener_nominas_parciales()

    browser = None
    page = None
    drive_service = None

    try:
        # Inicializar Playwright y Drive
        from playwright.async_api import async_playwright
        async_pw = async_playwright()
        p = await async_pw.__aenter__()
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(30000)
        drive_service = get_drive_service()

        # PASO 0: Login
        logger.info("=" * 80)
        logger.info("PASO 0: Iniciando sesión...")
        logger.info("=" * 80)
        await paso_0_login(page)
        logger.info("✓ Login completado")

        # PASO 1-1.6: Cartola
        cartola_path = await task_descargar_cartola_step(page, fecha_hoy)
        filas_nuevas = await task_procesar_cartola_step(cartola_path)
        task_subir_cartola_step(cartola_path, filas_nuevas, fecha_hoy, drive_service)

        # ETAPA 1: Nóminas parciales
        ids_procesados_etapa1 = await task_procesar_etapa1(
            page, nominas_parciales, fecha_hoy, drive_service, browser
        )

        # Reset después de ETAPA 1
        if ids_procesados_etapa1:
            logger.info("Reseteando navegador después de ETAPA 1...")
            logger.info("⏸️  Pausa de 30s para recuperación...")
            await asyncio.sleep(30)

            try:
                await page.click("nav a:has-text('Pagos')", timeout=10000)
                await asyncio.sleep(2)
            except:
                pass

            # Cerrar y abrir página nueva
            logger.info("=" * 80)
            logger.info("Cerrando página exhausta y abriendo nueva para PASO 2...")
            logger.info("=" * 80)
            await page.close()
            page = await browser.new_page()
            page.set_default_timeout(30000)
            await paso_0_login(page)
            logger.info("✓ Nueva sesión iniciada")

        # PASO 2-3.5: Nóminas nuevas
        logger.info("⏸️  Pausa de 10s antes de PASO 2...")
        await asyncio.sleep(10)
        await task_procesar_paso2(page, fecha_hoy, drive_service, browser, ids_procesados_etapa1)

        logger.info("=" * 80)
        logger.info("BOT COMPLETADO EXITOSAMENTE")
        logger.info("=" * 80)

    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"BOT FALLÓ: {e}")
        logger.error("=" * 80)
        raise

    finally:
        if page:
            try:
                await page.close()
            except:
                pass
        if browser:
            await browser.close()
            logger.info("Browser cerrado")


if __name__ == "__main__":
    import sys

    fecha_testing = None
    if len(sys.argv) > 1:
        fecha_testing = sys.argv[1]

    # Ejecutar directamente para testing local
    # En producción, usar: prefect deployment run 'valle-frio-bot-8am'
    try:
        asyncio.run(valle_frio_bot_flow(fecha_testing))
    except Exception as e:
        print(f"Error ejecutando flow: {e}")
        sys.exit(1)
