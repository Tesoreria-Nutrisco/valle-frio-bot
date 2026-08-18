"""
Cliente de conexión a GaussDB (Softland).
Extrae egresos de la cuenta de banco propio con contrapartida en productor.
"""

import logging
import psycopg2
import pandas as pd
from typing import List, Dict, Tuple
from datetime import datetime, timedelta
from config import (
    GAUSSDB_CONN, GAUSSDB_SCHEMA,
    CAPITAL_PROPIO, CUENTA_PRODUCTOR,
    BANCO_CUENTA_MAP, TIMEOUT_GAUSSDB
)

logger = logging.getLogger(__name__)


def obtener_egresos_softland(dias_atras: int = 30) -> List[Dict]:
    """
    Obtiene egresos Softland de Consorcio (10-01-10-16) + BCI (10-01-10-06 por bug conocido).
    Solo nóminas bancarias (cwcpbte.Proceso = 'emisión de nómina'), con contrapartida en productor 20-01-20-04.

    REGLA CONSORCIO↔BCI: Busca en ambas cuentas por bug conocido de Softland.
    FILTRO NÓMINA: Usa cwcpbte.Proceso='emisión de nómina' (no TipDocCb que mostraba valores incorrectos).

    Args:
        dias_atras: días de histórico a consultar desde hoy (default 30)

    Returns:
        Lista de dicts con: CpbAno, CpbNum, cuenta_banco, fecha, monto_egreso,
        productor_cod, monto_productor, glosa
    """
    logger.info(f"Consultando Softland: egresos Consorcio+BCI, nóminas, productor (últimos {dias_atras} días)")

    query = f"""
    SELECT
      b."CpbAno",
      b."CpbNum",
      TRIM(b."PctCod") AS cuenta_banco,
      b."CpbFec" AS fecha,
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
      AND b."CpbFec" >= CURRENT_DATE - INTERVAL '{dias_atras} days'
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

        logger.info(f"[OK] Extracción OK: {len(df)} movimientos encontrados")
        return df.to_dict('records')

    except Exception as e:
        logger.error(f"Error consultando Softland: {e}")
        raise


def obtener_contacto_productor(productor_cod: str) -> Tuple[str, str, str]:
    """
    Busca contactos del productor en Softland:
    1. cwtauxi.EMail
    2. cwtauxi.eMailDTE (fallback)
    3. cwtaxco.Email (fallback de contacto)

    Args:
        productor_cod: RUT/código auxiliar del productor (con o sin espacios)

    Returns:
        Tuple (email, email_dte, email_contacto) — None si no existe
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
            return None, None, None

        row = df.iloc[0]
        email = row['email'] if pd.notna(row['email']) and row['email'] else None
        email_dte = row['email_dte'] if pd.notna(row['email_dte']) and row['email_dte'] else None
        email_contacto = row['email_contacto'] if pd.notna(row['email_contacto']) and row['email_contacto'] else None

        logger.debug(f"Productor {productor_cod}: email={email}, email_dte={email_dte}, contacto={email_contacto}")
        return email, email_dte, email_contacto

    except Exception as e:
        logger.error(f"Error buscando contacto de {productor_cod}: {e}")
        return None, None, None
