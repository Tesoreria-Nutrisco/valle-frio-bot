import logging
import re
from pathlib import Path
from datetime import datetime
import pdfplumber
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extraer_metadatos_nomina(pdf_path):
    """
    Extrae metadatos de la nómina usando extracción de TABLAS estructuradas.

    Busca la tabla que contiene "ID nómina" y extrae:
    - "ID nómina"
    - "Fecha carga"
    - "Fecha pago"
    - "Estado"

    Returns:
        {
            'id_nomina': str,
            'fecha_carga': date,
            'fecha_pago': date,
            'estado': str
        }
    """
    pdf_path = Path(pdf_path)
    logger.info(f"Extrayendo metadatos de nómina (tablas): {pdf_path}")

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError("PDF vacío")

            page = pdf.pages[0]
            tables = page.extract_tables()

            if not tables:
                raise ValueError("No se encontraron tablas en la primera página")

            logger.info(f"Se encontraron {len(tables)} tabla(s) en página 1")

            id_nomina = None
            fecha_carga = None
            fecha_pago = None
            estado = None

            for table_idx, table in enumerate(tables):
                logger.debug(f"Tabla {table_idx}: {table}")

                for row_idx, row in enumerate(table):
                    row_str = str(row).lower()

                    if "id nómina" in row_str:
                        logger.info(f"Tabla {table_idx}, fila {row_idx}: encontrada 'ID nómina'")

                        header_row = None
                        data_row = None

                        if row_idx == 0 and "id nómina" in str(row[0]).lower():
                            header_row = row
                            if row_idx + 1 < len(table):
                                data_row = table[row_idx + 1]
                        elif row_idx > 0:
                            header_row = table[row_idx - 1] if row_idx > 0 else None
                            data_row = row

                        if header_row and data_row:
                            logger.debug(f"Header: {header_row}")
                            logger.debug(f"Data: {data_row}")

                            try:
                                idx_id = next(i for i, h in enumerate(header_row) if h and "id nómina" in str(h).lower())
                                idx_fecha_carga = next(i for i, h in enumerate(header_row) if h and "fecha carga" in str(h).lower())
                                idx_fecha_pago = next(i for i, h in enumerate(header_row) if h and "fecha pago" in str(h).lower())
                                idx_estado = next((i for i, h in enumerate(header_row) if h and "estado" in str(h).lower()), None)

                                id_nomina = str(data_row[idx_id]).strip() if idx_id < len(data_row) else None
                                fecha_carga_str = str(data_row[idx_fecha_carga]).strip() if idx_fecha_carga < len(data_row) else None
                                fecha_pago_str = str(data_row[idx_fecha_pago]).strip() if idx_fecha_pago < len(data_row) else None
                                estado = str(data_row[idx_estado]).strip() if idx_estado is not None and idx_estado < len(data_row) else None

                                logger.info(f"ID nómina: {id_nomina}")
                                logger.info(f"Fecha carga (str): {fecha_carga_str}")
                                logger.info(f"Fecha pago (str): {fecha_pago_str}")
                                logger.info(f"Estado: {estado}")

                                # Parsear fechas
                                if fecha_carga_str and fecha_carga_str != "None":
                                    try:
                                        fecha_carga = datetime.strptime(fecha_carga_str, "%d/%m/%Y").date()
                                        logger.info(f"Fecha carga parseada: {fecha_carga}")
                                    except Exception as e:
                                        logger.warning(f"No se pudo parsear Fecha carga '{fecha_carga_str}': {e}")

                                if fecha_pago_str and fecha_pago_str != "None":
                                    try:
                                        fecha_pago = datetime.strptime(fecha_pago_str, "%d/%m/%Y").date()
                                        logger.info(f"Fecha pago parseada: {fecha_pago}")
                                    except Exception as e:
                                        logger.warning(f"No se pudo parsear Fecha pago '{fecha_pago_str}': {e}")

                                if id_nomina:
                                    return {
                                        'id_nomina': id_nomina,
                                        'fecha_carga': fecha_carga,
                                        'fecha_pago': fecha_pago,
                                        'estado': estado
                                    }

                            except (StopIteration, IndexError) as e:
                                logger.warning(f"No se pudieron encontrar todas las columnas: {e}")
                                continue

            raise ValueError("No se encontró ID nómina en las tablas del PDF")

    except Exception as e:
        logger.error(f"Error extrayendo metadatos de nómina: {e}")
        raise


def extraer_ruts_nomina(pdf_path):
    """
    Parsea un PDF de nómina (Estado de Firmas) y extrae los RUTs de beneficiarios.

    Busca patrones de RUT en TODAS las páginas del "Detalle de nómina",
    excluyendo el RUT cliente que aparece en el resumen.
    Devuelve una lista de RUTs únicos de beneficiarios.
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        logger.error(f"PDF no existe: {pdf_path}")
        raise FileNotFoundError(f"PDF no existe: {pdf_path}")

    logger.info(f"Parseando PDF de nómina: {pdf_path}")

    ruts = set()
    rut_cliente = None

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            logger.info(f"PDF abierto: {len(pdf.pages)} páginas")

            # Primera pasada: extraer RUT cliente de la primera página
            if len(pdf.pages) > 0:
                text_pag1 = pdf.pages[0].extract_text()
                if text_pag1 and "RUT cliente" in text_pag1:
                    rut_pattern = r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]|\d{7,8}-[\dkK]"
                    matches = re.findall(rut_pattern, text_pag1)
                    if matches:
                        # El primer RUT después de "RUT cliente" es el cliente
                        rut_cliente = matches[0]
                        logger.info(f"RUT cliente identificado: {rut_cliente}")

            # Segunda pasada: encontrar dónde comienza "Detalle de nómina" y procesar TODAS las páginas desde ahí
            detalle_inicio = -1
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if text and "Detalle de nómina" in text:
                    detalle_inicio = page_num
                    logger.info(f"Sección 'Detalle de nómina' encontrada en página {page_num}")
                    break

            # Procesar TODAS las páginas desde "Detalle de nómina" hasta el final
            if detalle_inicio > 0:
                for page_num in range(detalle_inicio, len(pdf.pages) + 1):
                    page = pdf.pages[page_num - 1]
                    text = page.extract_text()

                    if not text:
                        logger.warning(f"No se extrajo texto de página {page_num}")
                        continue

                    logger.info(f"Procesando página {page_num} (detalle de nómina)")

                    # Buscar patrones de RUT
                    rut_pattern = r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]|\d{7,8}-[\dkK]"
                    matches = re.findall(rut_pattern, text)

                    logger.info(f"Encontrados {len(matches)} RUTs en página {page_num}")

                    for rut_str in matches:
                        rut_clean = rut_str.strip()

                        # Excluir el RUT cliente
                        if rut_clean and rut_clean != rut_cliente:
                            ruts.add(rut_clean)
                            logger.debug(f"RUT de beneficiario extraído: {rut_clean}")
            else:
                logger.warning("No se encontró 'Detalle de nómina' en el PDF")

    except Exception as e:
        logger.error(f"Error parseando PDF: {e}")
        raise

    ruts_list = sorted(list(ruts))
    logger.info(f"Se extrajeron {len(ruts_list)} RUTs únicos de beneficiarios: {ruts_list}")

    if not ruts_list:
        raise ValueError("No se extrajeron RUTs de beneficiarios del PDF de nómina")

    return ruts_list


def normalizar_rut(rut):
    """
    Normaliza un RUT: XX.XXX.XXX-X → XXXXXXXX-X
    """
    # Remover puntos
    rut_sin_puntos = rut.replace(".", "")
    return rut_sin_puntos


def extraer_ruts_nomina_excel(excel_path):
    """
    Extrae RUTs de beneficiarios de un archivo Excel de nómina.

    Busca la columna "RUT" en la tabla de detalles y extrae todos los RUTs únicos.

    Args:
        excel_path: Ruta al archivo .xlsx

    Returns:
        Lista de RUTs únicos de beneficiarios
    """
    import openpyxl

    excel_path = Path(excel_path)

    if not excel_path.exists():
        logger.error(f"Excel no existe: {excel_path}")
        raise FileNotFoundError(f"Excel no existe: {excel_path}")

    logger.info(f"Extrayendo RUTs de Excel: {excel_path}")

    ruts = set()
    rut_pattern = r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]|\d{7,8}-[\dkK]"

    try:
        wb = openpyxl.load_workbook(str(excel_path))
        ws = wb.active

        # Buscar encabezados y la columna RUT
        headers = []
        rut_column = None

        for row in ws.iter_rows(min_row=1, max_row=20, values_only=True):
            # Buscar fila con encabezados
            if any(cell and "rut" in str(cell).lower() for cell in row if cell):
                headers = row
                for idx, header in enumerate(headers):
                    if header and "rut" in str(header).lower():
                        rut_column = idx
                        break
                break

        if rut_column is None:
            logger.warning("No se encontró columna RUT en Excel, buscando por patrón")
            # Fallback: buscar cualquier celda con patrón de RUT
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell and isinstance(cell, str):
                        match = re.search(rut_pattern, str(cell))
                        if match:
                            ruts.add(match.group())
        else:
            # Extraer RUTs de la columna encontrada
            for row in ws.iter_rows(min_row=len(headers)+2, values_only=True):
                if row and rut_column < len(row):
                    cell_value = row[rut_column]
                    if cell_value and isinstance(cell_value, str):
                        match = re.search(rut_pattern, cell_value)
                        if match:
                            ruts.add(match.group())

        wb.close()

        ruts_list = sorted(list(ruts))
        logger.info(f"Se extrajeron {len(ruts_list)} RUTs de Excel: {ruts_list}")

        if not ruts_list:
            raise ValueError("No se extrajeron RUTs del Excel de nómina")

        return ruts_list

    except Exception as e:
        logger.error(f"Error extrayendo RUTs del Excel: {e}")
        raise
