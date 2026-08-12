#!/usr/bin/env python3
"""Script para limpiar las tablas de Supabase y empezar desde cero."""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("❌ Error: Faltan credenciales en .env")
    exit(1)

headers = {
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
    "Accept-Profile": "valle_frio_bot"
}

print("=" * 80)
print("LIMPIANDO BASE DE DATOS PARA PRUEBA DEFINITIVA")
print("=" * 80)

try:
    print("\n[1] Limpiando bot1_cartola_transacciones...")
    response = httpx.delete(
        f"{SUPABASE_URL}/rest/v1/bot1_cartola_transacciones",
        headers=headers
    )
    if response.status_code in [200, 204]:
        print("✓ Cartolas eliminadas")
    else:
        print(f"⚠ Respuesta: {response.text}")
except Exception as e:
    print(f"⚠ Error: {e}")

try:
    print("\n[2] Limpiando bot1_nominas_descargadas...")
    response = httpx.delete(
        f"{SUPABASE_URL}/rest/v1/bot1_nominas_descargadas",
        headers=headers
    )
    if response.status_code in [200, 204]:
        print("✓ Nóminas eliminadas")
    else:
        print(f"⚠ Respuesta: {response.text}")
except Exception as e:
    print(f"⚠ Error: {e}")

print("\n" + "=" * 80)
print("✅ BASE DE DATOS LIMPIA - Lista para prueba definitiva desde hoy")
print("=" * 80)
