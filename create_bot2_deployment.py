#!/usr/bin/env python3
"""
Crear deployment de Bot 2 en Prefect (igual a Bot 1)
Usa flow.deploy() para Prefect 3.7.5
"""

import sys
from pathlib import Path
from src.flows.bot2_flow import bot2_flow

def create_bot2_deployment():
    """Crear deployment de Bot 2 usando flow.deploy()"""

    print("🚀 Creando deployment de Bot 2...")
    print("   (igual a la configuración de Bot 1)")

    try:
        # Usar flow.deploy() para Prefect 3.7.5
        deployment = bot2_flow.deploy(
            name="bot2-reconciliation",
            work_pool_name="lenovo-rpa-pool",
            tags=["bot2", "reconciliacion"],
            ignore_warnings=True
        )

        print(f"\n✅ Deployment creado exitosamente!")
        print(f"   Nombre: bot2-reconciliation")
        print(f"   Flow: bot2-reconciliation")
        print(f"   Work Pool: lenovo-rpa-pool")
        print(f"   Tags: bot2, reconciliacion")

        print(f"\n📌 Para ejecutar Bot 2 en Prefect:")
        print(f"   prefect deployment run 'bot2-reconciliation/bot2-reconciliation'")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_bot2_deployment()
    sys.exit(0 if success else 1)
