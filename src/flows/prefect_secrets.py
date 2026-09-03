#!/usr/bin/env python3
"""
Carga las credenciales desde Prefect Secret Blocks al entorno del proceso.

bot1/config.py y bot2/config.py leen os.getenv() al importarse, y en el worker
no existe .env (el repo se clona limpio desde GitHub en cada corrida). Este
módulo puebla os.environ desde los Secret Blocks ANTES de esos imports.

En local el .env sigue funcionando como fallback: si un bloque no está
disponible, el valor que ya venga en el entorno se conserva.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Secret Block en Prefect -> variable de entorno que espera config.py
SECRETOS = {
    # Banco Consorcio
    "banco-usuario": "BANCO_USUARIO",
    "banco-clave": "BANCO_CLAVE",
    # Google Drive (service account completa, la consume drive_utils)
    "google-credentials-valle-frio": "GOOGLE_CREDENTIALS_JSON",
    # Google Drive (IDs de carpetas)
    "drive-folder-cartolas": "DRIVE_FOLDER_ID_CARTOLAS",
    "drive-folder-comprobantes": "DRIVE_FOLDER_ID_COMPROBANTES",
    "drive-folder-comprobantes-nominas": "DRIVE_FOLDER_ID_COMPROBANTES_NOMINAS",
    "drive-folder-nominas": "DRIVE_FOLDER_ID_NOMINAS",
    # Supabase
    "supabase-url": "SUPABASE_URL",
    "supabase-service-role-key": "SUPABASE_SERVICE_ROLE_KEY",
    # GaussDB / Softland (solo Bot 2)
    "gaussdb-host": "GAUSSDB_HOST",
    "gaussdb-port": "GAUSSDB_PORT",
    "gaussdb-db": "GAUSSDB_DB",
    "gaussdb-user": "GAUSSDB_USER",
    "gaussdb-password": "GAUSSDB_PASSWORD",
}


async def cargar_secretos() -> None:
    """
    Puebla os.environ desde los Secret Blocks.

    Debe llamarse ANTES de importar bot1.config / bot2.config: esos módulos
    resuelven os.getenv() en tiempo de import, no de uso.
    """
    from prefect.blocks.system import Secret

    cargados = []
    faltantes = []

    for bloque, variable in SECRETOS.items():
        try:
            secret = await Secret.load(bloque)
            valor = secret.get()
        except Exception as e:
            faltantes.append(f"{bloque} ({type(e).__name__})")
            continue

        if valor is None or valor == "":
            faltantes.append(f"{bloque} (vacío)")
            continue

        # Los bloques que guardan JSON (ej. la service account de Drive) vuelven
        # como dict; str() daría repr de Python, no JSON válido.
        if isinstance(valor, (dict, list)):
            valor = json.dumps(valor)

        os.environ[variable] = str(valor)
        cargados.append(variable)

    logger.info(f"Secretos cargados desde Prefect: {len(cargados)}/{len(SECRETOS)}")
    if faltantes:
        # No es fatal: en local el .env cubre lo que falte.
        logger.warning(f"Bloques no disponibles: {', '.join(faltantes)}")


class _PuenteLogsPrefect(logging.Handler):
    """Reenvía los logs de los módulos del bot al run logger de Prefect."""

    def emit(self, record):
        try:
            from prefect import get_run_logger

            get_run_logger().log(record.levelno, self.format(record))
        except Exception:
            # Fuera de un flow run (ej. ejecución local) no hay nada que hacer.
            pass


# Librerías que inundarían la UI: httpx logea cada request a Supabase.
RUIDOSOS = (
    "httpx",
    "httpcore",
    "urllib3",
    "googleapiclient",
    "google",
    "google_auth_httplib2",
    "asyncio",
    "playwright",
    "charset_normalizer",
)


def conectar_logs(*_modulos: str) -> None:
    """
    Hace visibles en la UI de Prefect los logs de los módulos del bot.

    Se engancha al logger raíz en vez de a nombres concretos: según cómo Prefect
    importe el entrypoint, un mismo módulo puede registrarse como 'run' o como
    'bot2.run', y enumerarlos a mano deja fuera justo el que falló.
    """
    puente = _PuenteLogsPrefect()
    puente.setFormatter(logging.Formatter("%(name)s - %(message)s"))

    raiz = logging.getLogger()
    # Idempotente: la task puede reintentarse dentro del mismo proceso.
    if not any(isinstance(h, _PuenteLogsPrefect) for h in raiz.handlers):
        raiz.addHandler(puente)
    raiz.setLevel(logging.INFO)

    for nombre in RUIDOSOS:
        logging.getLogger(nombre).setLevel(logging.WARNING)
