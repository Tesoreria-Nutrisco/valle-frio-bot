import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Rutas
PROJECT_ROOT = Path(__file__).parent
CREDENTIALS_PATH = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH")
TEMP_DOWNLOAD_PATH = Path(os.getenv("DOWNLOAD_TEMP_PATH", PROJECT_ROOT / "temp_downloads"))
LOG_PATH = Path(os.getenv("LOG_PATH", PROJECT_ROOT / "logs"))

# Google Drive
DRIVE_FOLDER_ID_CARTOLAS = os.getenv("DRIVE_FOLDER_ID_CARTOLAS")
DRIVE_FOLDER_ID_COMPROBANTES = os.getenv("DRIVE_FOLDER_ID_COMPROBANTES")

# Banco
BANCO_USUARIO = os.getenv("BANCO_USUARIO")
BANCO_CLAVE = os.getenv("BANCO_CLAVE")
BANCO_NOMBRE_CARPETA = os.getenv("BANCO_NOMBRE_CARPETA", "consorcio")

# Modo
MODO_DRY_RUN = os.getenv("MODO_DRY_RUN", "false").lower() == "true"

# URLs banco
BANCO_URL_LOGIN = "https://servicios.bancoconsorcio.cl/BancaEmpresas"
BANCO_URL_CUENTAS = "https://servicios.bancoconsorcio.cl/BancaEmpresas/cuentas"

# Crear carpetas si no existen
TEMP_DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.mkdir(parents=True, exist_ok=True)

# Validaciones
if not CREDENTIALS_PATH or not Path(CREDENTIALS_PATH).exists():
    raise FileNotFoundError(f"Credenciales de Google no encontradas en {CREDENTIALS_PATH}")

if not BANCO_USUARIO or not BANCO_CLAVE:
    raise ValueError("BANCO_USUARIO y BANCO_CLAVE son requeridos en .env")

if not DRIVE_FOLDER_ID_CARTOLAS or not DRIVE_FOLDER_ID_COMPROBANTES:
    raise ValueError("IDs de carpetas de Drive son requeridos en .env")
