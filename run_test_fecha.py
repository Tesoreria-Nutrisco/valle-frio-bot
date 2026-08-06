#!/usr/bin/env python3
"""
Script de testing con una fecha específica.
Úsalo para probar con fechas que sabemos tienen datos.
"""

import asyncio
from datetime import datetime
from run import main

if __name__ == "__main__":
    # CAMBIA ESTA FECHA PARA PROBAR DIFERENTES DÍAS
    # TEST_DATE = datetime(2026, 7, 29)  # Día 29 (página 2)
    # TEST_DATE = datetime(2026, 7, 28)  # Día 28 (con datos)
    # TEST_DATE = datetime(2026, 7, 22)  # Día 22 (página 1)
    from datetime import timedelta
    TEST_DATE = datetime.now() - timedelta(days=1)  # Ayer

    print(f"Testing con fecha: {TEST_DATE.strftime('%d/%m/%Y')}")
    asyncio.run(main(TEST_DATE))
