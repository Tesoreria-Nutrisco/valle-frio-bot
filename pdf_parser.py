import logging
import re
from pathlib import Path
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def extraer_ruts_nomina(pdf_path):
    """
    Parsea un PDF de nómina (Estado de Firmas) y extrae los RUTs de beneficiarios.

    Busca patrones de RUT solo en la sección "Detalle de nómina" (últimas páginas),
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
        reader = PdfReader(str(pdf_path))
        logger.info(f"PDF abierto: {len(reader.pages)} páginas")

        # Primera pasada: extraer RUT cliente de la primera página
        if len(reader.pages) > 0:
            text_pag1 = reader.pages[0].extract_text()
            if text_pag1 and "RUT cliente" in text_pag1:
                rut_pattern = r"\d{1,2}\.\d{3}\.\d{3}-[\dkK]|\d{7,8}-[\dkK]"
                matches = re.findall(rut_pattern, text_pag1)
                if matches:
                    # El primer RUT después de "RUT cliente" es el cliente
                    rut_cliente = matches[0]
                    logger.info(f"RUT cliente identificado: {rut_cliente}")

        # Segunda pasada: extraer RUTs de beneficiarios (páginas con "Detalle de nómina")
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()

            if not text:
                logger.warning(f"No se extrajo texto de página {page_num}")
                continue

            # Solo procesar si contiene "Detalle de nómina" o "Beneficiario"
            if "Detalle de nómina" not in text and "Beneficiario" not in text:
                continue

            logger.info(f"Procesando página {page_num} (contiene Detalle de nómina)")

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
