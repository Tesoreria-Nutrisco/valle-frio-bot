#!/usr/bin/env python3
"""
Deploy script para Valle Frío Bot - Python puro (sin YAML)

Crea UN ÚNICO deployment que se ejecuta 3 veces al día:
- 8:00 AM (lunes a viernes)
- 12:00 PM (lunes a viernes)
- 18:00 PM (lunes a viernes)

Uso:
    python deploy.py

Comandos útiles después:
    prefect deployment ls
    prefect deployment run 'valle-frio-bot'
    prefect deployment logs 'valle-frio-bot'
"""

import sys
from datetime import datetime
from pathlib import Path

try:
    from prefect import flow
    from prefect.schedules import Cron
except ImportError as e:
    print(f"ERROR: No se pudo importar Prefect: {e}")
    print("Instala con: pip install prefect==3.7.5")
    sys.exit(1)

# Importar el flow
try:
    from src.flows.valle_frio_bot_flow import valle_frio_bot_flow
except ImportError as e:
    print(f"ERROR importando flow: {e}")
    print("Asegúrate de estar en la raíz del proyecto valle-frio-bot")
    sys.exit(1)


def deploy():
    """Despliega el Valle Frío Bot Flow con UN ÚNICO deployment y 3 schedules."""
    print("=" * 80)
    print("PREFECT DEPLOY: Valle Frío Bot")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    # Cron que ejecuta a las 8:00, 12:00 y 18:00 (lunes a viernes)
    # Formato: min hour day month weekday
    # 0 8,12,18 * * 1-5 = min 0, horas 8/12/18, cualquier día, cualquier mes, lunes-viernes
    schedule = Cron("0 8,12,18 * * 1-5")

    print("Deployment: valle-frio-bot")
    print(f"Descripción: Bot de descarga de cartolas y comprobantes - Banco Consorcio")
    print(f"Schedule: Cron 0 8,12,18 * * 1-5 (8 AM, 12 PM, 6 PM lunes-viernes)")
    print(f"Work Pool: lenovo-rpa-pool")
    print()

    try:
        # Usar flow.serve() para crear y registrar el deployment
        # flow.serve() es el método recomendado en Prefect 3.7.5+
        print("Registrando deployment en Prefect server...")
        print()

        # Crear el deployment usando flow.serve()
        # Esto registra el flow con los parámetros especificados
        valle_frio_bot_flow.serve(
            name="valle-frio-bot",
            description="Bot de descarga de cartolas y comprobantes - Banco Consorcio",
            schedule=schedule,
            parameters={},
        )

    except Exception as e:
        print(f"✗ Error durante deploy: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    deploy()
