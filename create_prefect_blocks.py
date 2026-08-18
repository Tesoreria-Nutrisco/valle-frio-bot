#!/usr/bin/env python3
"""
Script para crear bloques Secret en Prefect Cloud desde el .env local
Ejecutar: python create_prefect_blocks.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
import os

# Cargar .env
load_dotenv()

# Importar después de cargar .env
from prefect.blocks.system import Secret

PROJECT_ROOT = Path(__file__).parent

# Bloques a crear: (nombre_bloque, valor)
BLOQUES = {
    "banco-usuario": os.getenv("BANCO_USUARIO"),
    "banco-clave": os.getenv("BANCO_CLAVE"),
    "drive-folder-cartolas": os.getenv("DRIVE_FOLDER_ID_CARTOLAS"),
    "drive-folder-comprobantes": os.getenv("DRIVE_FOLDER_ID_COMPROBANTES"),
    "drive-folder-nominas": os.getenv("DRIVE_FOLDER_ID_NOMINAS"),
    "supabase-url": os.getenv("SUPABASE_URL"),
    "supabase-service-role-key": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    "gaussdb-host": os.getenv("GAUSSDB_HOST"),
    "gaussdb-port": os.getenv("GAUSSDB_PORT"),
    "gaussdb-db": os.getenv("GAUSSDB_DB"),
    "gaussdb-user": os.getenv("GAUSSDB_USER"),
    "gaussdb-password": os.getenv("GAUSSDB_PASSWORD"),
}

def main():
    print("=" * 80)
    print("CREANDO BLOQUES SECRET EN PREFECT")
    print("=" * 80)
    print()

    # Crear bloques regulares
    for nombre, valor in BLOQUES.items():
        if valor:
            try:
                Secret(value=valor).save(nombre, overwrite=True)
                print(f"✓ {nombre:40} creado exitosamente")
            except Exception as e:
                print(f"✗ {nombre:40} ERROR: {e}")
        else:
            print(f"⚠ {nombre:40} valor no encontrado en .env")

    # Crear bloque de Google Drive Credentials (JSON)
    print()
    print("Creando bloque Google Drive Credentials (JSON)...")
    credentials_path = PROJECT_ROOT / "credentials.json"
    if credentials_path.exists():
        try:
            with open(credentials_path, "r") as f:
                credentials_json = json.dumps(json.load(f))
            Secret(value=credentials_json).save("google-drive-credentials-json", overwrite=True)
            print(f"✓ {'google-drive-credentials-json':40} creado exitosamente")
        except Exception as e:
            print(f"✗ {'google-drive-credentials-json':40} ERROR: {e}")
    else:
        print(f"⚠ {'google-drive-credentials-json':40} credentials.json no encontrado")

    print()
    print("=" * 80)
    print("✓ Bloques creados en Prefect Cloud")
    print("=" * 80)
    print()
    print("Próximos pasos:")
    print("1. Verifica los bloques en: https://prefect.nutriscohub.com/blocks")
    print("2. Actualiza el flow para que use estos bloques")
    print()

if __name__ == "__main__":
    main()
