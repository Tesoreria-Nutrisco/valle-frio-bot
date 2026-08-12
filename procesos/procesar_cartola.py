"""
PASO 1.5: Procesar cartola descargada.
- Lee el Excel descargado (soporta XLS antiguo y XLSX moderno)
- Verifica cada transacción en Supabase
- Registra las nuevas (evita duplicados)
- Retorna lista de filas nuevas para subir a Drive
"""

import logging
from pathlib import Path
import pandas as pd
from supabase_client import verificar_cartola_transaccion, insertar_cartola_transaccion

logger = logging.getLogger(__name__)


async def paso_1_5_procesar_cartola(cartola_path: Path) -> list:
    """
    Procesa la cartola descargada.
    Soporta XLS (antiguo) y XLSX (moderno).

    Args:
        cartola_path: Ruta al archivo Excel descargado

    Returns:
        Lista de diccionarios con filas nuevas (no duplicadas)
        Formato: [{
            'num_transaccion': '...',
            'fecha_contable': date,
            'monto': float,
            'fila_excel': list (valores de la fila para subir a Drive)
        }, ...]
    """
    logger.info(f"PASO 1.5: Procesando cartola {cartola_path.name}...")

    filas_nuevas = []

    try:
        # Leer con pandas sin encabezado (XLS tiene formato con espacios en blanco al inicio)
        df_raw = pd.read_excel(cartola_path, engine='xlrd' if str(cartola_path).endswith('.xls') else None, header=None)
        logger.info(f"Archivo cargado: {len(df_raw)} filas totales")

        # Buscar la fila de encabezados (contiene "Num.")
        header_row_idx = None
        for idx, row in df_raw.iterrows():
            if "Num." in row.values:
                header_row_idx = idx
                logger.info(f"Encabezados encontrados en fila {idx}")
                break

        if header_row_idx is None:
            raise ValueError("No se encontró fila con encabezados (Num.)")

        # Usar esa fila como encabezado y procesar datos posteriores
        df = pd.DataFrame(df_raw.iloc[header_row_idx + 1:].values, columns=df_raw.iloc[header_row_idx].values)
        df = df.dropna(how='all')  # Eliminar filas completamente vacías

        logger.info(f"Columnas encontradas: {df.columns.tolist()}")
        logger.info(f"Filas de datos: {len(df)}")

        # Verificar que existen las columnas esperadas
        columnas_esperadas = ["Num.", "Fecha Contable"]
        for col in columnas_esperadas:
            if col not in df.columns:
                logger.error(f"Columna faltante: {col}. Disponibles: {df.columns.tolist()}")
                raise ValueError(f"No se encontró columna requerida: {col}")

        # Procesar cada fila
        for idx, row in df.iterrows():
            try:
                num_transaccion = row["Num."]
                fecha_contable = row["Fecha Contable"]

                # Determinar monto: usar Cargos o Abonos (uno de los dos tiene valor)
                cargos = row.get("Cargos", None)
                abonos = row.get("Abonos", None)
                monto = cargos if pd.notna(cargos) and cargos != 0 else abonos

                # Saltar filas vacías
                if pd.isna(num_transaccion) or pd.isna(fecha_contable):
                    logger.debug(f"Fila {idx}: vacía, saltando")
                    continue

                # Verificar si ya existe en Supabase
                if verificar_cartola_transaccion(str(num_transaccion)):
                    logger.debug(f"Transacción {num_transaccion} ya existe, ignorando")
                    continue

                # Es nueva → insertar en Supabase
                monto_valor = float(monto) if pd.notna(monto) else 0
                insertar_cartola_transaccion(
                    str(num_transaccion),
                    fecha_contable,
                    monto_valor
                )
                logger.info(f"✓ Nueva transacción registrada: {num_transaccion} - {fecha_contable} - {monto_valor}")

                # Agregar a lista de nuevas
                fila_values = row.tolist()
                filas_nuevas.append({
                    'num_transaccion': str(num_transaccion),
                    'fecha_contable': fecha_contable,
                    'monto': monto_valor,
                    'fila_excel': fila_values
                })

            except Exception as e:
                logger.warning(f"Error procesando fila {idx}: {e}")
                continue

        logger.info(f"✓ Se encontraron {len(filas_nuevas)} transacciones nuevas")
        return filas_nuevas

    except Exception as e:
        logger.error(f"Error procesando cartola: {e}")
        raise
