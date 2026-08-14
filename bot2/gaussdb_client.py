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
    Obtiene egresos en cuenta de banco propio (capital NB) donde existe
    contrapartida en cuenta de productor 20-01-20-04 con MovDebe > 0.

    Args:
        dias_atras: días de histórico a consultar desde hoy

    Returns:
        Lista de dicts con: CpbAno, CpbNum, PctCod (cuenta banco),
        CpbFec, MovHaber (monto), y líneas de productor (CodAux, MovDebe, MovGlosa)
    """
    logger.info(f"Consultando Softland: egresos de {CAPITAL_PROPIO} con productor (últimos {dias_atras} días)")

    fecha_desde = (datetime.now() - timedelta(days=dias_atras)).date()
    fecha_hasta = datetime.now().date()

    query = f"""
    SELECT
        m1.CpbAno,
        m1.CpbNum,
        p1.PctCod AS cuenta_banco,
        m1.CpbFec,
        m1.MovHaber AS monto_egreso,
        m2.CodAux AS productor_cod,
        m2.MovDebe AS productor_monto,
        m2.MovGlosa,
        m1.TipDocCb
    FROM
        {GAUSSDB_SCHEMA}.cwmovim m1
        INNER JOIN {GAUSSDB_SCHEMA}.cwpctas p1 ON m1.CpbAno = p1.CpbAno AND m1.CpbNum = p1.CpbNum AND m1.CpbCod = p1.PctCod
        INNER JOIN {GAUSSDB_SCHEMA}.cwmovim m2 ON m1.CpbAno = m2.CpbAno AND m1.CpbNum = m2.CpbNum
        INNER JOIN {GAUSSDB_SCHEMA}.cwpctas p2 ON m2.CpbAno = p2.CpbAno AND m2.CpbNum = p2.CpbNum AND m2.CpbCod = p2.PctCod
    WHERE
        -- Egreso en cuenta de banco propio
        p1.PctCod IN (SELECT PctCod FROM {GAUSSDB_SCHEMA}.cwpctas WHERE Cpbano = {CAPITAL_PROPIO})
        AND m1.MovDebe = 0  -- Es egreso (Debe = 0 significa Haber)
        AND m1.MovHaber > 0
        -- Contrapartida en cuenta de productor
        AND p2.PctCod = '{CUENTA_PRODUCTOR}'
        AND m2.MovDebe > 0  -- Monto adeudado al productor
        -- Rango de fechas
        AND m1.CpbFec BETWEEN '{fecha_desde}' AND '{fecha_hasta}'
    ORDER BY
        m1.CpbFec DESC, m1.CpbNum DESC
    """

    try:
        conn = psycopg2.connect(**GAUSSDB_CONN, connect_timeout=TIMEOUT_GAUSSDB)
        df = pd.read_sql(query, conn)
        conn.close()

        # TRIM de campos varchar
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip()

        logger.info(f"✓ Extracción OK: {len(df)} movimientos encontrados")
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
        productor_cod: RUT/código auxiliar del productor

    Returns:
        Tuple (email, email_dte, email_contacto) — None si no existe
    """
    query = f"""
    SELECT
        TRIM(aux.EMail) AS email,
        TRIM(aux.eMailDTE) AS email_dte,
        TRIM(COALESCE(con.Email, '')) AS email_contacto,
        aux.Nombre
    FROM
        {GAUSSDB_SCHEMA}.cwtauxi aux
        LEFT JOIN {GAUSSDB_SCHEMA}.cwtaxco con ON aux.CodAux = con.CodAuc
    WHERE
        aux.CodAux = '{productor_cod}'
    LIMIT 1
    """

    try:
        conn = psycopg2.connect(**GAUSSDB_CONN, connect_timeout=TIMEOUT_GAUSSDB)
        df = pd.read_sql(query, conn)
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
