"""
Cliente de conexión a GaussDB (Softland).
Extrae egresos de la cuenta de banco propio con contrapartida en productor.
"""

import logging
import psycopg2
import pandas as pd
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Importar config desde bot2 (no bot1)
bot2_path = Path(__file__).parent
sys.path.insert(0, str(bot2_path))

from config import (
    GAUSSDB_CONN, GAUSSDB_SCHEMA,
    CAPITAL_PROPIO, CUENTA_PRODUCTOR,
    BANCO_CUENTA_MAP, TIMEOUT_GAUSSDB
)

logger = logging.getLogger(__name__)


def obtener_egresos_softland(dias_atras: int = 30, fecha_hasta: datetime = None) -> List[Dict]:
    """
    Obtiene egresos Softland de Consorcio (10-01-10-16) + BCI (10-01-10-06 por bug conocido).
    Solo nóminas bancarias (cwcpbte.Proceso = 'emisión de nómina'), con contrapartida en productor 20-01-20-04.

    Args:
        dias_atras: días de histórico a consultar hacia atrás (default 30)
        fecha_hasta: Fecha límite superior (default: datetime.now()).
                    En modo testing: usar la fecha simulada para buscar solo hacia atrás desde esa fecha.
                    En producción: usar None para que sea hoy.

    Returns:
        Lista de dicts con: CpbAno, CpbNum, cuenta_banco, fecha, monto_egreso,
        productor_cod, monto_productor, glosa
    """
    if fecha_hasta is None:
        fecha_hasta = datetime.now()

    fecha_desde = (fecha_hasta - timedelta(days=dias_atras)).date()
    fecha_hasta_date = fecha_hasta.date() if isinstance(fecha_hasta, datetime) else fecha_hasta

    logger.info(f"Consultando Softland: egresos Consorcio+BCI, nóminas, productor ({fecha_desde} a {fecha_hasta_date})")

    # Usar fecha_desde y fecha_hasta en lugar de CURRENT_DATE - INTERVAL
    query = f"""
    SELECT
      b."CpbAno",
      b."CpbNum",
      TRIM(b."PctCod") AS cuenta_banco,
      b."CpbFec" AS fecha_carga,
      b."MovHaber" AS monto_egreso,
      TRIM(p."CodAux") AS productor_cod,
      p."MovDebe" AS monto_productor,
      p."MovGlosa" AS glosa
    FROM "SOFTLAND_VALLEFRIO"."cwmovim" b
    JOIN "SOFTLAND_VALLEFRIO"."cwmovim" p
      ON b."CpbAno" = p."CpbAno"
      AND b."CpbNum" = p."CpbNum"
    JOIN "SOFTLAND_VALLEFRIO"."cwcpbte" c
      ON b."CpbAno" = c."CpbAno"
      AND b."CpbNum" = c."CpbNum"
    WHERE c."Proceso" = 'emisión de nómina'
      AND TRIM(b."PctCod") IN ('10-01-10-16', '10-01-10-06')
      AND b."MovHaber" > 0
      AND TRIM(p."PctCod") = '20-01-20-04'
      AND p."MovDebe" > 0
      AND b."CpbFec" >= '{fecha_desde}'::DATE
      AND b."CpbFec" <= '{fecha_hasta_date}'::DATE
    ORDER BY b."CpbFec" DESC;
    """

    try:
        conn = psycopg2.connect(**GAUSSDB_CONN, connect_timeout=TIMEOUT_GAUSSDB)
        df = pd.read_sql(query, conn)
        conn.close()

        # TRIM de campos varchar
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip()

        # Convertir fecha_carga a string YYYY-MM-DD para matcher
        if 'fecha_carga' in df.columns:
            df['fecha_carga'] = pd.to_datetime(df['fecha_carga']).dt.strftime('%Y-%m-%d')

        logger.info(f"[OK] Extracción OK: {len(df)} movimientos encontrados")
        return df.to_dict('records')

    except Exception as e:
        logger.error(f"Error consultando Softland: {e}")
        raise


def obtener_contacto_productor(productor_cod: str) -> Tuple[str, str, str, str]:
    """
    Busca contactos del productor en Softland:
    1. cwtauxi.EMail
    2. cwtauxi.eMailDTE (fallback)
    3. cwtaxco.Email (fallback de contacto)

    Args:
        productor_cod: RUT/código auxiliar del productor (con o sin espacios)

    Returns:
        Tuple (email, email_dte, email_contacto, nombre) — None si no existe
    """
    query = """
    SELECT
        TRIM("EMail") AS email,
        TRIM("eMailDTE") AS email_dte,
        TRIM(COALESCE("Email", '')) AS email_contacto,
        TRIM("NomAux") AS nombre
    FROM
        "SOFTLAND_VALLEFRIO"."cwtauxi" aux
        LEFT JOIN "SOFTLAND_VALLEFRIO"."cwtaxco" con
          ON TRIM(aux."CodAux") = TRIM(con."CodAuc")
    WHERE
        TRIM(aux."CodAux") = %s
    LIMIT 1
    """

    try:
        conn = psycopg2.connect(**GAUSSDB_CONN, connect_timeout=TIMEOUT_GAUSSDB)
        df = pd.read_sql(query, conn, params=(productor_cod.strip(),))
        conn.close()

        if df.empty:
            logger.warning(f"Productor {productor_cod} no encontrado en Softland")
            return None, None, None, None

        row = df.iloc[0]
        email = row['email'] if pd.notna(row['email']) and row['email'] else None
        email_dte = row['email_dte'] if pd.notna(row['email_dte']) and row['email_dte'] else None
        email_contacto = row['email_contacto'] if pd.notna(row['email_contacto']) and row['email_contacto'] else None
        nombre = row['nombre'] if pd.notna(row['nombre']) and row['nombre'] else None

        logger.debug(f"Productor {productor_cod}: nombre={nombre}, email={email}, email_dte={email_dte}, contacto={email_contacto}")
        return email, email_dte, email_contacto, nombre

    except Exception as e:
        logger.error(f"Error buscando contacto de {productor_cod}: {e}")
        return None, None, None, None
