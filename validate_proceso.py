#!/usr/bin/env python3
"""
Validación de la query con el nuevo filtro: c.Proceso = 'emisión de nómina'
Busca específicamente el comprobante 00023091 que debe estar presente.
"""
import sys
sys.path.insert(0, 'bot2')

import psycopg2
import pandas as pd
from config import GAUSSDB_CONN, TIMEOUT_GAUSSDB

query = """
SELECT
  b."CpbAno",
  b."CpbNum",
  TRIM(b."PctCod") AS cuenta_banco,
  b."CpbFec" AS fecha,
  b."MovHaber" AS monto_egreso,
  TRIM(p."CodAux") AS productor_cod,
  p."MovDebe" AS monto_productor,
  p."MovGlosa" AS glosa,
  c."Proceso" AS proceso_origen,
  TRIM(b."TipDocCb") AS tip_doc_cb
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
  AND b."CpbFec" >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY b."CpbFec" DESC;
"""

try:
    conn = psycopg2.connect(**GAUSSDB_CONN, connect_timeout=TIMEOUT_GAUSSDB)
    df = pd.read_sql(query, conn)
    conn.close()

    print(f"Total egresos encontrados: {len(df)}")
    print()

    # Buscar específicamente el comprobante 00023091
    cpb_23091 = df[df['CpbNum'] == '00023091']
    if len(cpb_23091) > 0:
        print("✓ COMPROBANTE 00023091 ENCONTRADO")
        print()
        print(cpb_23091.to_string())
    else:
        print("✗ COMPROBANTE 00023091 NO ENCONTRADO")
        print("\nPrimeros 10 comprobantes encontrados:")
        print(df.head(10)[['CpbAno', 'CpbNum', 'fecha', 'monto_egreso', 'proceso_origen', 'tip_doc_cb']].to_string())

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
