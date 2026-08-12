# Valle Frío Bot - Proceso A (Bot de Cartolas y Nóminas)

## Descripción General

Bot automatizado para descargar y procesar **cartolas bancarias** y **nóminas de pago** del Banco Consorcio, extrayendo datos estructurados, deduplicando información y almacenando comprobantes en Google Drive.

**Objetivo:** Prevenir duplicados de descargas y mantener un registro centralizado de todas las transacciones y comprobantes procesados.

---

## 🔧 Tecnologías Utilizadas

| Componente | Tecnología | Propósito |
|-----------|-----------|----------|
| **Automatización web** | Playwright (async) | Navegar banco, hacer clics, descargar archivos |
| **Extracción de PDF** | `pdfplumber` | Extraer tablas estructuradas (metadatos) |
| **Extracción de PDF** | `PyPDF` | Extraer texto plano (RUTs beneficiarios) |
| **Excel (Cartola)** | `pandas` + `xlrd` | Leer ambos formatos: XLS (legacy OLE) y XLSX |
| **Base de datos** | Supabase PostgreSQL | Schema `valle_frio_bot` para estado de descargas |
| **Google Drive** | `google-api-python-client` | Subir archivos a Shared Drives |
| **Logging** | Python `logging` | Archivo + consola con timestamps |

---

## 📋 Flujo Completo del Bot (7 Pasos)

### **PASO 0: Autenticación en Banco Consorcio**

**Archivo:** `procesos/login.py`

**Entrada:** Credenciales en `.env`

**Tecnología:** Playwright
- Navega a `https://servicios.bancoconsorcio.cl/BancaEmpresas`
- Rellena RUT en input HTML
- Rellena contraseña
- Hace clic en botón "Ingresar"
- Selecciona empresa "VALLE FRIO SPA"

**Salida:** Sesión autenticada para pasos posteriores

---

### **PASO 1: Descargar Cartola (Excel)**

**Archivo:** `procesos/descargar_cartola.py`

**Entrada:** Sesión autenticada

**Tecnología:** Playwright + navegación HTML
1. Navega: Menú superior "Cuentas" → "Saldos y movimientos"
2. Selecciona cuenta CLP (4210026191)
3. **NO filtra por fecha** (descarga últimos 30-90 días que el banco proporciona)
4. Hace clic "Buscar"
5. Espera a que carguen resultados
6. Hace clic dropdown "Descargar" → "EXCEL"
7. Descarga archivo

**Salida:** `temp_downloads/cartolas/cartola_YYYYMMDD.xlsx`

---

### **PASO 1.5: Procesar Cartola (Deduplicación)**

**Archivo:** `procesos/procesar_cartola.py`

**Entrada:** Archivo Excel descargado

**Tecnología:** `pandas` + `xlrd`
- Lee Excel (soporta XLS OLE Compound + XLSX moderno)
- Busca encabezado con columnas: "Num.", "Fecha Contable", "Descripción", "Cargos", "Abonos", "Saldo"
- Para cada fila de datos:
  - Extrae: `num_transaccion`, `fecha_contable`, `monto`
  - Consulta Supabase: "¿Existe este `num_transaccion`?"
  - Si **no existe**: inserta en `bot1_cartola_transacciones` + agrega a lista "nuevas"
  - Si **existe**: salta (ya procesada)
- Retorna solo las filas nuevas

**Salida:**
- Lista de transacciones nuevas
- BD: Inserts en `bot1_cartola_transacciones`

---

### **PASO 1.6: Subir Cartola a Google Drive**

**Archivo:** `run.py` (líneas ~97-111)

**Entrada:** Archivo Excel + lista de filas nuevas

**Tecnología:** Google Drive API v3 (Shared Drives)
- Si lista de nuevas está **vacía**: salta (no sube nada)
- Si hay nuevas:
  - Busca/crea estructura: `Shared Drive > consorcio > 2026 > 08 > 07/`
  - Sube archivo con nombre: `cartola_consorcio_20260807.xlsx`

**Salida:** Archivo en Google Drive

---

### **PASO 2: Descargar Nómina (PDF) - Multi-nómina por Monto**

**Archivo:** `procesos/descargar_nomina.py`

**Entrada:** Sesión autenticada

**Tecnología:** Playwright + JavaScript + monto filtering

**Novedad:** Soporta múltiples nóminas del mismo día aislando por monto

1. Navega: "Pagos" → "Consultar" (Pago nómina)
2. Lee tabla de nóminas: extrae ID + Monto de cada fila
3. **Para cada nómina encontrada:**
   - Filtra por **monto exacto** en campos "Desde" y "Hasta"
     - Input "Desde": `monto_nomina` (ej: `$73.384.191`)
     - Input "Hasta": `monto_nomina + 1` (ej: `$73.384.192`)
   - Esto aísla UNA SOLA fila en la tabla
4. Abre dropdown de acciones
5. Hace clic en "Descarga PDF"
6. Descarga archivo con nombre: `nomina_YYYYMMDD_ID_NOMINA.pdf`
7. Limpia filtro de monto y continúa con siguiente nómina

**Ventaja:** Descarga todas las nóminas del mismo día sin duplicar

**Salida:** `temp_downloads/nominas/nomina_YYYYMMDD_IDNOMINA.pdf` (una por cada nómina)

---

### **PASO 2.5: Extraer Metadatos de Nómina**

**Archivo:** `pdf_parser.py` → `extraer_metadatos_nomina()`

**Entrada:** PDF descargado

**Tecnología:** `pdfplumber.extract_tables()`
- Abre PDF con pdfplumber
- Extrae **tablas estructuradas** de página 1 (NO regex en texto plano)
- Busca tabla con encabezado: "ID nómina | Tipo operación | Fecha carga | Fecha pago | Estado"
- Extrae celda por celda:
  - **ID nómina:** `1964514`
  - **Fecha carga:** `06/08/2026` → parseada a `date(2026, 8, 6)`
  - **Fecha pago:** `07/08/2026` → parseada a `date(2026, 8, 7)` ← **CRÍTICO para comprobantes**
  - **Estado:** `Completada` | `Autorización en Proceso` | `Anulación Automática`

**Salida:** Dict `{'id_nomina': str, 'fecha_carga': date, 'fecha_pago': date, 'estado': str}`

---

### **PASO 2.5.5: Validar Estado de Nómina**

**Archivo:** `run.py` (líneas ~135-155)

**Entrada:** Estado extraído del PDF

**Lógica:**
- ✅ **"Completada"** → continúa normalmente (extraer RUTs)
- ⏳ **"Autorización en Proceso"** → salta (aún no autorizada, no hay comprobantes)
- ❌ **"Anulación Automática"** → salta (será anulada, no procesarla)

**Salida:** Lista de RUTs = `[]` si estado inválido, si no procede a PASO 2.5.6

---

### **PASO 2.5.6: Extraer RUTs de Beneficiarios - Multi-página**

**Archivo:** `pdf_parser.py` → `extraer_ruts_nomina()`

**Entrada:** PDF descargado

**Tecnología:** `pdfplumber` + regex (todas las páginas)

**Novedad:** Extrae RUTs de TODAS las páginas del "Detalle de nómina"

1. **Primera pasada:** Identifica "RUT cliente" en página 1 (descarta)
2. **Segunda pasada:** Busca página con "Detalle de nómina"
3. **Tercera pasada - CRÍTICA:** Procesa TODAS las páginas desde "Detalle de nómina" hasta el final
   - Antes: Solo procesaba una página (perdía 15+ RUTs)
   - Ahora: Extrae todas las páginas del detalle
4. **Regex pattern:**
   - Formato largo: `\d{1,2}\.\d{3}\.\d{3}-[\dkK]` → `76.334.187-9`
   - Formato corto: `\d{7,8}-[\dkK]` → fallback
5. Filtra duplicados (mismo beneficiario puede tener 2+ pagos)
6. Retorna lista ordenada

**Salida:** Lista completa de RUTs: `['76.334.187-9', '76.763.393-9', ..., '77.713.645-3']` (20+ RUTs posibles)

---

### **PASO 2.6: Verificar Nómina en Supabase**

**Archivo:** `run.py` (líneas ~162-171) + `supabase_client.py` → `verificar_nomina()`

**Entrada:** ID nómina extraído

**Tecnología:** Supabase RPC + Python client

**Lógica:**
1. Consulta tabla `bot1_nominas_descargadas` por `id_nomina`
2. Tres casos:
   - **Existe + estado='completo':** Salta nómina (ya completada, no hacer nada)
   - **Existe + estado='parcial':** Continúa SIN reinsertar (reintento limpio)
   - **No existe:** Inserta como `'parcial'` (primera descarga)

**Salida:**
- BD: Nuevo registro en `bot1_nominas_descargadas`
- Control de flujo: permite PASO 3 o salta

---

### **PASO 3: Descargar Comprobantes Individuales**

**Archivo:** `procesos/descargar_comprobantes.py` → `paso_3_descargar_todos_comprobantes()`

**Entrada:** 
- Lista de RUTs únicos
- `fecha_pago` (del PDF, no fecha de hoy)
- `folder_id_comprobantes` (para búsqueda en Drive)

**Tecnología:** Playwright + Google Drive API
- Para cada RUT:
  1. Navega: "Pagos" → "Consultar" → "Consulta Histórica"
  2. Rellena formulario:
     - **RUT Beneficiario:** `76.334.187-9`
     - **Convenio:** `517`
     - **Desde (date picker):** `fecha_pago` (ej: `07/08/2026`)
     - **Hasta (date picker):** `fecha_pago` (MISMO día, filtro exacto)
  3. Hace clic "Filtrar"
  4. **Deduplicación en Drive:**
     - Busca en Drive: `comprobante_consorcio_YYYYMMDD_RUT.pdf`
     - Si **existe**: retorna `(rut, None)` (salta descarga)
     - Si **no existe**: continúa
  5. Busca y hace clic botón "Descargar"
  6. Espera descarga
  7. Guarda en temp: `comprobante_20260807_XXXXXXXX.pdf`

**Salida:** Lista de tuplas `[(rut, path), ...]` donde `path` puede ser `None` si ya existía

---

### **PASO 3.5: Subir Comprobantes a Google Drive**

**Archivo:** `run.py` (líneas ~177-199)

**Entrada:** Lista de tuplas `[(rut, path), ...]`

**Tecnología:** Google Drive API

**Lógica:**
1. Para cada comprobante:
   - Si `path is None`: **salta** (ya estaba en Drive)
   - Si `path` es válida: sube a Drive con nombre `comprobante_consorcio_YYYYMMDD_RUT.pdf`
2. Cuenta total procesados (nuevos + existentes)
3. Si **todos los RUTs tienen comprobante:**
   - Actualiza BD: `bot1_nominas_descargadas` → estado=`'completo'`
   - Guarda: `ruta_drive` = folder_id
4. Si **alguno falló:**
   - Deja como `'parcial'` (reintentará en próxima corrida)

**Salida:**
- Archivos en Drive: `consorcio/2026/08/07/comprobante_*.pdf`
- BD: Nómina marcada como `'completo'`

---

## 🔄 Estados de Nómina y Reintentos

### Máquina de Estados (4 estados)

```
DETECCIÓN EN PDF
    ↓
    ├─ "Anulación Automática" → ANULADA (ignorar, rechazada por banco)
    ├─ "Autorización Pendiente" → PENDIENTE (reintenta próxima corrida)
    └─ "Completada" → continúa
       ↓
       NO EXISTE en BD
          ↓
       [INSERT como 'parcial']
          ↓
       INTENTA PASO 3 (descargar comprobantes)
          ↓
          ├─ ✅ Todos OK → UPDATE a 'completo'
          │  ↓
          │  COMPLETO (nómina lista, salta en futuras corridas)
          │
          └─ ❌ Alguno falló → Queda 'parcial'
             ↓
             [Próxima corrida]
             ├─ Verifica: ya existe como 'parcial' → NO reinsertar
             ├─ Intenta PASO 3 de nuevo
             ├─ Si todos OK: UPDATE a 'completo'
             └─ Si aún falla: Queda 'parcial' (reintenta próxima vez)
```

### Tabla de Estados

| Estado | Significado | Qué hace bot en próxima corrida |
|--------|-----------|--------------------------------|
| **No existe** | Nómina nueva | Inserta + intenta PASO 3 |
| **'anulada'** | Rechazada/Anulada por banco automático | Ignora completamente (no hace nada) |
| **'pendiente'** | Autorización aún no completada | Reintenta (verifica si cambió a 'completo') |
| **'parcial'** | Comprobantes parcialmente descargados | **Reintenta PASO 3 sin reinsertar** |
| **'completo'** | Todos comprobantes descargados | Salta completamente |

### Ejemplo de Ciclo de Reintentos

```
CORRIDA 1 (Nómina ID 1964514 - nueva):
├─ INSERT bot1_nominas_descargadas → 'parcial'
├─ PASO 3: Intenta descargar RUT1, RUT2, RUT3
├─ RUT1 ✓ OK
├─ RUT2 ✓ OK
├─ RUT3 ❌ TIMEOUT (error de red)
└─ Queda como 'parcial'

CORRIDA 2 (Mismo día, reintentar):
├─ Verifica: id_nomina=1964514 → estado='parcial'
├─ PASO 2.6: NO reinsertar (clave para evitar duplicate key)
├─ PASO 3: Intenta descargar RUT1, RUT2, RUT3 de nuevo
├─ RUT1 ✓ Ya en Drive → saltea
├─ RUT2 ✓ Ya en Drive → saltea
├─ RUT3 ✓ Descarga ésta vez
├─ Todos completados → UPDATE a 'completo'
└─ Nómina lista

CORRIDA 3+ (Mismo o futuro día):
├─ Verifica: id_nomina=1964514 → estado='completo'
└─ Salta completamente (no hace nada)
```

---

## 💾 Tablas de Supabase (Schema `valle_frio_bot`)

### `bot1_cartola_transacciones`
```sql
CREATE TABLE valle_frio_bot.bot1_cartola_transacciones (
  id SERIAL PRIMARY KEY,
  num_transaccion TEXT UNIQUE NOT NULL,
  fecha_contable DATE NOT NULL,
  monto NUMERIC NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```
**Propósito:** Evitar reinsertar las mismas filas de cartola  
**Índice:** `num_transaccion` (búsqueda rápida)  
**Limpieza:** `DELETE FROM valle_frio_bot.bot1_cartola_transacciones;`

### `bot1_nominas_descargadas`
```sql
CREATE TABLE valle_frio_bot.bot1_nominas_descargadas (
  id SERIAL PRIMARY KEY,
  id_nomina TEXT UNIQUE NOT NULL,
  fecha_carga DATE NOT NULL,
  fecha_pago DATE NOT NULL,
  estado TEXT CHECK (estado IN ('anulada', 'pendiente', 'parcial', 'completo')) DEFAULT 'parcial',
  ruta_drive TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```
**Propósito:** Rastrear nóminas y sus estados (anulada/pendiente/parcial/completo)  
**Índice:** `id_nomina` (búsqueda rápida)  
**Campo `ruta_drive`:** Folder ID en Google Drive donde se guardaron comprobantes  

**Estados:**
- `'anulada'`: Rechazada por banco (no procesar)
- `'pendiente'`: Autorización en proceso (reintenta próxima vez)
- `'parcial'`: Algunos comprobantes descargados (reintenta próxima vez)
- `'completo'`: Todos comprobantes descargados (listo, ignora)

**Limpieza:** `DELETE FROM valle_frio_bot.bot1_nominas_descargadas;`

---

## 🔌 Funciones RPC en Supabase (Schema `public`)

Todas las funciones usan `SET search_path = valle_frio_bot` como workaround para que Python client pueda acceder sin problemas de header `Accept-Profile`.

### `insertar_cartola`
```sql
CREATE OR REPLACE FUNCTION public.insertar_cartola(
  p_num_transaccion TEXT,
  p_fecha_contable DATE,
  p_monto NUMERIC
) RETURNS VOID AS $$
SET search_path = valle_frio_bot;
INSERT INTO bot1_cartola_transacciones (num_transaccion, fecha_contable, monto)
VALUES (p_num_transaccion, p_fecha_contable, p_monto);
$$ LANGUAGE SQL;
```

### `insertar_nomina`
```sql
CREATE OR REPLACE FUNCTION public.insertar_nomina(
  p_id_nomina TEXT,
  p_fecha_carga DATE,
  p_fecha_pago DATE,
  p_estado TEXT DEFAULT 'parcial'
) RETURNS VOID AS $$
SET search_path = valle_frio_bot;
INSERT INTO bot1_nominas_descargadas (id_nomina, fecha_carga, fecha_pago, estado)
VALUES (p_id_nomina, p_fecha_carga, p_fecha_pago, p_estado);
$$ LANGUAGE SQL;
```

### `actualizar_nomina`
```sql
CREATE OR REPLACE FUNCTION public.actualizar_nomina(
  p_id_nomina TEXT,
  p_estado TEXT
) RETURNS VOID AS $$
SET search_path = valle_frio_bot;
UPDATE bot1_nominas_descargadas 
SET estado = p_estado, updated_at = NOW()
WHERE id_nomina = p_id_nomina;
$$ LANGUAGE SQL;
```

---

## 📁 Estructura de Archivos

```
valle-frio-bot/
├── run.py                          ← PUNTO DE ENTRADA (ejecutar esto)
├── supabase_client.py              # Funciones Supabase (verificar, insertar, actualizar)
├── pdf_parser.py                   # Extracción PDF (metadatos + RUTs)
├── drive_utils.py                  # Google Drive API (búsqueda, upload)
├── config.py                       # Configuración global (paths, IDs, constantes)
│
├── procesos/
│   ├── login.py                    # PASO 0: Autenticación
│   ├── descargar_cartola.py        # PASO 1: Descarga Excel
│   ├── procesar_cartola.py         # PASO 1.5: Deduplicación Excel
│   ├── descargar_nomina.py         # PASO 2: Descarga PDF
│   └── descargar_comprobantes.py   # PASO 3: Descarga comprobantes
│
├── requirements.txt                # Dependencias: playwright, pdfplumber, pandas, supabase, etc.
├── .env                            # Variables de entorno (NUNCA en git)
├── cleanup_db.py                   # Script para limpiar Supabase (pruebas)
│
├── logs/                           # Logs automáticos con timestamp
│   └── bot_20260807_100717.log
│
├── temp_downloads/                 # Archivos descargados (organizados en subcarpetas)
│   ├── cartolas/                   # Cartolas Excel por fecha
│   │   ├── cartola_20260807.xlsx
│   │   ├── cartola_20260808.xlsx
│   │   └── ...
│   └── nominas/                    # Nóminas PDF (una por cada ID descargado)
│       ├── nomina_20260807_1965890.pdf
│       ├── nomina_20260807_1965892.pdf
│       └── ...
│
└── README.md                       # Este archivo
```

---

## 🚀 Instalación y Uso

### Instalar Dependencias
```bash
cd C:\Users\jpmunoz\valle-frio-bot
venv\Scripts\activate
pip install -r requirements.txt
```

### Ejecutar Bot
```bash
python run.py
```

### Limpiar BD (Pruebas Limpias)
```bash
python cleanup_db.py
```

### Variables de Entorno (.env)
```env
# Supabase
SUPABASE_URL=https://zczzcvlpvnwevoxfosdp.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Google Drive
GOOGLE_CREDENTIALS_PATH=./credentials.json

# Banco Consorcio
BANCO_RUT=20.430.968-K
BANCO_PASSWORD=***
```

---

## 📌 Mejoras Recientes (v2.0)

### 🎯 Descarga Multi-Nómina por Monto
- **Problema anterior:** Bot solo descargaba la nómina más reciente cuando había múltiples del mismo día
- **Solución:** Implementar monto filtering (Desde=monto_exacto, Hasta=monto+1) para aislar cada nómina
- **Resultado:** Descarga TODAS las nóminas del mismo día sin duplicar

### 📄 Extracción Multi-página de RUTs
- **Problema anterior:** Bot solo extraía RUTs de la primera página del "Detalle de nómina" (4 RUTs máximo)
- **Solución:** Cambiar de PyPDF a pdfplumber + procesar TODAS las páginas desde "Detalle de nómina" hasta el final
- **Resultado:** Extrae 20+ RUTs correctamente

### 📁 Organización de Carpetas
- **Problema anterior:** Todos los archivos se guardaban en `temp_downloads/` (raíz)
- **Solución:** Separar en `temp_downloads/nominas/` y `temp_downloads/cartolas/`
- **Resultado:** Estructura limpia y organizada

### 🔄 Estados Extendidos
- **Anterior:** Solo 'parcial' y 'completo'
- **Ahora:** 'anulada', 'pendiente', 'parcial', 'completo'
- **Ventaja:** Maneja nóminas rechazadas (anulada) y en proceso de autorización (pendiente)

---

## ⚡ Características Clave

### ✅ Deduplicación Multinivel
1. **Cartola:** Por `num_transaccion` (tabla Supabase)
2. **Nómina:** Por `id_nomina` con estados `'parcial'/'completo'`
3. **Comprobantes:** Búsqueda en Google Drive antes de descargar

### ✅ Reintentos Inteligentes
- Nóminas en estado `'parcial'` reintentan sin reinsertar
- Evita `duplicate key` errors
- Salta comprobantes que ya están en Drive

### ✅ Validación de Estado (4 Estados)
- **"Completada"** → Procesa normalmente (descarga comprobantes)
- **"Autorización Pendiente"** → Marca como 'pendiente' y reintenta próxima corrida
- **"Anulación Automática"** → Marca como 'anulada' e ignora (rechazada por banco)
- Evita procesar nóminas inválidas

### ✅ Fecha de Pago Correcta
- Usa `fecha_pago` del PDF, no fecha de ejecución del bot
- Permite procesar nóminas de días anteriores

### ✅ Schema Explícito
- Todas las BD en `valle_frio_bot` (con underscore)
- NUNCA escribe en schema `public`

---

## 📝 Logs

Cada ejecución genera log con timestamp:
```
logs/bot_20260807_100717.log
```

**Ejemplo de log:**
```
2026-08-07 10:08:22,730 - __main__ - INFO - Extrayendo metadatos de nómina...
2026-08-07 10:08:22,730 - pdf_parser - INFO - ID nómina: 1964514
2026-08-07 10:08:22,730 - pdf_parser - INFO - Fecha pago parseada: 2026-08-07
2026-08-07 10:08:22,730 - pdf_parser - INFO - Estado: Completada
2026-08-07 10:08:22,730 - __main__ - INFO - Se encontraron 4 RUTs únicos
2026-08-07 10:08:22,587 - __main__ - INFO - Descargando comprobantes para 4 RUTs...
2026-08-07 10:08:38,474 - procesos.descargar_comprobantes - INFO - Fechas ingresadas: 07/08/2026
```

---

## 🐛 Troubleshooting

### "No API key found in request"
→ Supabase header `apikey` o `Authorization` faltando

### "Duplicate key violation on num_transaccion"
→ Cartola ya fue procesada (normal, se salta)

### "Could not find the table in the schema cache"
→ Schema `public` en lugar de `valle_frio_bot` (workaround con RPC functions)

### "Timeout esperando descarga"
→ Banco no tiene datos para ese RUT en esa fecha

### "Estado inválido para procesar"
→ Nómina no es "Completada" (está en proceso o fue anulada)
