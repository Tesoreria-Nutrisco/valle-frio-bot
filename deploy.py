#!/usr/bin/env python3
"""
Deploy script para Valle Frío Bot - Prefect Cloud con from_source()

Crea UN ÚNICO deployment que se ejecuta 3 veces al día en lenovo-rpa-pool:
- 8:00 AM (lunes a viernes)
- 12:00 PM (lunes a viernes)
- 18:00 (6 PM) (lunes a viernes)

Uso:
    python deploy.py

Comandos útiles después:
    prefect deployment ls
    prefect deployment run 'valle-frio-bot'
"""

import sys
from datetime import datetime

try:
    from prefect import flow
    from prefect.schedules import Cron
except ImportError as e:
    print(f"ERROR: No se pudo importar Prefect: {e}")
    print("Instala con: pip install prefect==3.7.5")
    sys.exit(1)


def deploy():
    """Despliega el Valle Frío Bot Flow desde GitHub en lenovo-rpa-pool."""
    print("=" * 80)
    print("PREFECT DEPLOY: Valle Frío Bot")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    schedule = Cron("0 8,12,18 * * 1-5")

    print("Deployment: valle-frio-bot")
    print(f"Descripción: Bot de descarga de cartolas y comprobantes - Banco Consorcio")
    print(f"Fuente: https://github.com/javieramunozc/valle-frio-bot.git")
    print(f"Entrypoint: src/flows/valle_frio_bot_flow.py:valle_frio_bot_flow")
    print(f"Schedule: 0 8,12,18 * * 1-5 (8 AM, 12 PM, 6 PM lunes-viernes)")
    print(f"Work Pool: lenovo-rpa-pool")
    print()

    try:
        print("Registrando deployment en Prefect Cloud...")

        flow.from_source(
            source="https://github.com/javieramunozc/valle-frio-bot.git",
            entrypoint="src/flows/valle_frio_bot_flow.py:valle_frio_bot_flow",
        ).deploy(
            name="valle-frio-bot",
            description="Bot de descarga de cartolas y comprobantes - Banco Consorcio",
            work_pool_name="lenovo-rpa-pool",
            cron="0 8,12,18 * * 1-5",
            tags=["valle-frio", "consorcio"],
        )

        print()
        print("✓ Deployment registrado exitosamente en Prefect Cloud")
        print()
        print("Próximas ejecuciones programadas:")
        print("  - 08:00 (lunes-viernes)")
        print("  - 12:00 (lunes-viernes)")
        print("  - 18:00 (lunes-viernes)")
        print()
        print("Ver en: https://prefect.nutriscohub.com/deployments")

    except Exception as e:
        print(f"✗ Error durante deploy: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    deploy()
