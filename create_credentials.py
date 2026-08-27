#!/usr/bin/env python3
"""
Script para crear credentials.json a partir de un Prefect Secret Block.
Se usa como deployment step en prefect.yaml.
"""

import json
import os
from pathlib import Path

def create_credentials_from_block():
    """
    Crea credentials.json leyendo desde variables de entorno o archivo local.
    """
    # Intentar leer el archivo local si existe
    local_creds = Path("./credentials.json")
    if local_creds.exists():
        print(f"✓ credentials.json ya existe en {local_creds}")
        return True

    # Alternativa: si existe archivo en otra ubicación
    alt_path = Path.home() / "valle-frio-bot" / "credentials.json"
    if alt_path.exists():
        import shutil
        shutil.copy(alt_path, local_creds)
        print(f"✓ credentials.json copiado desde {alt_path}")
        return True

    # Si no existe, advertir
    print("⚠️  credentials.json no encontrado. El bot necesitará acceso a Google Drive.")
    print(f"   Ubicaciones buscadas:")
    print(f"   - ./credentials.json (actual)")
    print(f"   - {alt_path}")

    return False

if __name__ == "__main__":
    create_credentials_from_block()
