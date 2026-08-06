# Bot de Descarga de Cartolas y Comprobantes - Banco Consorcio

Automatiza la descarga de cartolas y comprobantes de nómina del banco Consorcio y los sube a Google Drive.

## Instalación rápida

```bash
cd C:\Users\jpmunoz\valle-frio-bot
venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

```bash
python run.py
```

Para prueba sin subir a Drive:
```bash
set MODO_DRY_RUN=true
python run.py
```

## Estructura del proyecto

```
valle-frio-bot/
├── run.py                      ← EJECUTAR ESTO
├── config.py                   # Configuración y variables de entorno
├── drive_utils.py              # Funciones de Google Drive
├── pdf_parser.py               # Parsear PDFs y extraer RUTs
│
├── procesos/                   # Los 4 pasos del bot (ordenados)
│   ├── 0_login.py              # Paso 0: Login en el banco
│   ├── 1_descargar_cartola.py  # Paso 1: Descargar Excel de movimientos
│   ├── 2_descargar_nomina.py   # Paso 2: Descargar PDF de nómina
│   └── 3_descargar_comprobantes.py  # Paso 3: Descargar comprobantes por RUT
│
├── .env                        # Variables de entorno (user/clave)
├── credentials.json            # Service account de Google
├── requirements.txt            # Dependencias Python
│
├── logs/                       # Logs automáticos
├── temp_downloads/             # Archivos descargados (temporal)
└── README.md
```

## Flujo del bot

1. **Login** → Autentica en servicios.bancoconsorcio.cl
2. **Cartola** → Descarga Excel de "Últimos movimientos" → Sube a Drive
3. **Nómina** → Descarga PDF "Estado de Firmas" → Parsea RUTs únicos
4. **Comprobantes** → Por cada RUT, descarga su comprobante individual → Sube a Drive

**Estructura en Drive:**
```
Cartolas/
  └── consorcio/AAAA/MM/DD/cartola_consorcio_YYYYMMDD.xlsx

Comprobantes/
  └── consorcio/AAAA/MM/DD/comprobante_consorcio_YYYYMMDD_RUT.pdf
```

## Configuración (.env)

```ini
BANCO_USUARIO=20.430.968-K
BANCO_CLAVE=Cons_2108
GOOGLE_DRIVE_CREDENTIALS_PATH=C:\Users\jpmunoz\valle-frio-bot\credentials.json
DRIVE_FOLDER_ID_CARTOLAS=1wIMazNNEGuCV29kJwHfIgM_HiTFGcF_Z
DRIVE_FOLDER_ID_COMPROBANTES=1kXrCcPI9xflRB0l59tvdd9xy5v2cEVfq
BANCO_NOMBRE_CARPETA=consorcio
MODO_DRY_RUN=false
```

## Logs

```
logs/bot_20260805_143022.log
```

Cada ejecución genera un log con timestamp. También se imprime en consola.

## Cambiar selectores del banco

Si el portal del banco cambia, actualiza los selectores en:
- `procesos/0_login.py` → inputs y botón de login
- `procesos/1_descargar_cartola.py` → navegación y botón de descarga
- `procesos/2_descargar_nomina.py` → navegación y botón de descarga
- `procesos/3_descargar_comprobantes.py` → formulario de búsqueda y botón de PDF

Usa DevTools (F12) para encontrar los selectores correctos.

## Notas

- El bot NO hace matching ni decisiones de negocio
- Si no encuentra RUTs, el bot se detiene con error
- Si un RUT individual falla, continúa con los siguientes
- DRY_RUN simula todo sin tocar Drive
- Los archivos temporales en `temp_downloads/` no se borran automáticamente
