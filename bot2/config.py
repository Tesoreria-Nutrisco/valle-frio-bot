import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ============================================================
# RUTAS
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
BOT2_ROOT = PROJECT_ROOT / "bot2"
TEMPLATES_PATH = BOT2_ROOT / "templates"
LOG_PATH = Path(os.getenv("LOG_PATH", PROJECT_ROOT / "logs"))

# Crear directorios si no existen
TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.mkdir(parents=True, exist_ok=True)

# ============================================================
# GAUSSDB (Softland)
# ============================================================
GAUSSDB_HOST = os.getenv("GAUSSDB_HOST", "10.252.0.149")
GAUSSDB_PORT = int(os.getenv("GAUSSDB_PORT", "8000"))
GAUSSDB_DB = os.getenv("GAUSSDB_DB", "gaussdb")
GAUSSDB_USER = os.getenv("GAUSSDB_USER", "CtasCorp")
GAUSSDB_PASSWORD = os.getenv("GAUSSDB_PASSWORD")
GAUSSDB_SCHEMA = "SOFTLAND_VALLEFRIO"

GAUSSDB_CONN = {
    "host": GAUSSDB_HOST,
    "port": GAUSSDB_PORT,
    "database": GAUSSDB_DB,
    "user": GAUSSDB_USER,
    "password": GAUSSDB_PASSWORD,
    "client_encoding": "utf8",
}

# ============================================================
# SUPABASE (Bot 2 state + Bot 1 shared)
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_SCHEMA = "valle_frio_bot"

# ============================================================
# GOOGLE DRIVE (reutiliza Bot 1)
# ============================================================
GOOGLE_DRIVE_CREDENTIALS_PATH = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH")
DRIVE_FOLDER_ID_CARTOLAS = os.getenv("DRIVE_FOLDER_ID_CARTOLAS")
DRIVE_FOLDER_ID_COMPROBANTES = os.getenv("DRIVE_FOLDER_ID_COMPROBANTES")
TEAM_DRIVE_ID = "0AAy1zHCqHR5ZUk9PVA"  # Shared Drive de Valle Frío

# ============================================================
# GMAIL API (notificaciones)
# ============================================================
GMAIL_SERVICE_ACCOUNT = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH")  # Reutilizar credenciales
GMAIL_SENDER = "projects.treasury.finance@nutrisco.com"  # Remitente de correos
GMAIL_REPLY_TO = "projects.treasury.finance@nutrisco.com"

# ============================================================
# BOT 2 CONFIGURACIÓN
# ============================================================
CAPITAL_PROPIO = "NB"  # Fase 1: solo NB
CUENTA_PRODUCTOR = "20-01-20-04"  # Fruta Nacional Pesos
BANCO_CONSORCIO = "CONSORCIO"

# Modo de prueba (default: true — activar explícitamente para producción)
MODO_TEST = os.getenv("MODO_TEST", "true").lower() == "true"
CORREO_PRUEBA = os.getenv("CORREO_PRUEBA", "javiera.munozc@nutrisco.com")  # Correo destino en modo prueba

# Mapeo: banco → cuentas a buscar en Softland (workaround Consorcio↔BCI)
BANCO_CUENTA_MAP = {
    "CONSORCIO": ["10-01-10-16", "10-01-10-06"],  # Cuenta propia + BCI (bug conocido)
    # Agregar otros bancos aquí según sea necesario
}

# ============================================================
# REINTENTOS Y TIMEOUTS
# ============================================================
MAX_INTENTOS_MATCH_MISMA_CORRIDA = 3
TIMEOUT_GAUSSDB = 30
TIMEOUT_DRIVE = 30
TIMEOUT_SUPABASE = 30

# ============================================================
# VALIDACIONES
# ============================================================
if not GAUSSDB_PASSWORD:
    raise ValueError("GAUSSDB_PASSWORD no configurada en .env")
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Credenciales Supabase no configuradas en .env")
if not GOOGLE_DRIVE_CREDENTIALS_PATH or not Path(GOOGLE_DRIVE_CREDENTIALS_PATH).exists():
    raise ValueError(f"Credenciales Google Drive no encontradas en {GOOGLE_DRIVE_CREDENTIALS_PATH}")
if not DRIVE_FOLDER_ID_CARTOLAS or not DRIVE_FOLDER_ID_COMPROBANTES:
    raise ValueError("IDs de carpetas Google Drive no configurados en .env")
