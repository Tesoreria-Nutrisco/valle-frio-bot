#!/usr/bin/env python3
"""
Setup Bot 2 deployment en Prefect 3.7.5
"""

import sys
from pathlib import Path

# Crear un script de deployment simple
def create_deployment_yaml():
    """Crear archivo YAML de deployment para Prefect"""

    yaml_content = """
name: execute_bot2
description: Bot 2 - Reconciliación Softland vs Cartola (TEST)

flow:
  entrypoint: bot2_executor:execute_bot2

deployments:
  - name: bot2-test
    description: Bot 2 - Reconciliación Softland vs Cartola (TEST)
    entrypoint: bot2_executor:execute_bot2
    tags:
      - bot2
      - reconciliacion
      - test
    parameters:
      fecha_prueba: null
    schedules: []
    work_queue: default
"""

    print("🚀 Configurando Bot 2 en Prefect...")
    print(f"   Working dir: {Path.cwd()}")

    try:
        yaml_path = Path("bot2_deployment.yaml")
        yaml_path.write_text(yaml_content.strip())

        print(f"\n✅ Deployment creado:")
        print(f"   Archivo: {yaml_path}")
        print(f"   Nombre: execute_bot2/bot2-test")
        print(f"   Tags: bot2, reconciliacion, test")

        print(f"\n📌 Para desplegar en Prefect:")
        print(f"   prefect deploy -f {yaml_path}")

        print(f"\n📌 Para ejecutar:")
        print(f"   prefect deployment run 'execute_bot2/bot2-test'")

        print(f"\n📌 O ejecutar manualmente:")
        print(f"   python bot2_executor.py [fecha]")

        print(f"\n✅ ¡Listo para subirlo a Prefect!")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_deployment_yaml()
    sys.exit(0 if success else 1)
