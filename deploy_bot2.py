#!/usr/bin/env python3
"""
Deploy Bot 2 a Prefect en el work pool lenovo-rpa-pool
"""

import subprocess
import sys
from pathlib import Path

def deploy_bot2():
    """Crear deployment de Bot 2 en Prefect"""

    print("🚀 Deployando Bot 2 a Prefect...")
    print(f"   Work Pool: lenovo-rpa-pool")

    # Crear archivo deployment.yaml
    deployment_yaml = """
name: execute_bot2
description: Bot 2 - Reconciliación Softland vs Cartola

flow:
  entrypoint: bot2_executor:execute_bot2
  path: .

deployments:
  - name: bot2-reconciliation
    description: Bot 2 - Reconciliación Softland vs Cartola
    entrypoint: bot2_executor:execute_bot2
    tags:
      - bot2
      - reconciliacion
    parameters:
      fecha_prueba: null
    work_pool_name: lenovo-rpa-pool
    version: "1.0.0"
"""

    # Guardar YAML
    yaml_path = Path("bot2_deployment.yaml")
    with open(yaml_path, "w") as f:
        f.write(deployment_yaml)

    print(f"✓ Archivo deployment guardado: {yaml_path}")

    # Aplicar deployment
    print("\nAplicando deployment a Prefect...")
    try:
        result = subprocess.run(
            ["prefect", "deployment", "apply", str(yaml_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print("✓ Deployment aplicado exitosamente")
            print(f"\n✅ Bot 2 está en Prefect!")
            print(f"   Nombre: execute_bot2/bot2-reconciliation")
            print(f"   Work Pool: lenovo-rpa-pool")
            print(f"\n📌 Para ejecutar:")
            print(f"   prefect deployment run 'execute_bot2/bot2-reconciliation'")
            return True
        else:
            print(f"⚠️  Deployment output: {result.stdout}")
            print(f"⚠️  Error: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ Timeout al aplicar deployment")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = deploy_bot2()
    sys.exit(0 if success else 1)
