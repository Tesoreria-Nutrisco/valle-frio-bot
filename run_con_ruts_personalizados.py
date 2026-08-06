#!/usr/bin/env python3
"""
Ejecuta el flujo completo (Pasos 1, 2, 3) pero con RUTs personalizados
"""

import asyncio
from datetime import datetime
from run import main

if __name__ == "__main__":
    # RUTs de la foto (del 5 de agosto)
    RUTS_PRUEBA = [
        '11.233.358-4',
        '13.683.040-6',
        '14.248.133-2',
        '15.939.685-1',
        '16.254.492-6',
        '17.131.376-7',
        '17.008.810-3',
        '19.008.810-3',
        '76.022.442-1',
        '76.033.522-3',
        '76.197.861-6',
        '76.212.570-6'
    ]

    print(f"Ejecutando con {len(RUTS_PRUEBA)} RUTs personalizados")
    asyncio.run(main(ruts_personalizados=RUTS_PRUEBA))
