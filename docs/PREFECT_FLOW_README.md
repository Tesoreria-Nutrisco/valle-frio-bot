# Valle Frío Bot - Prefect Flow

Este documento describe cómo usar el nuevo Prefect Flow para ejecutar el bot de descarga de cartolas y comprobantes.

## Estructura

- `src/flows/valle_frio_bot_flow.py` - Prefect flow refactorizado
- `deploy.py` - Script de deploy con 3 schedules
- `bot1/run.py` - Código original (mantenido para referencia)

## Características del Flow

### 1. Patrón Dual de Secretos

El flow implementa un patrón dual para cargar secretos:

```python
def get_secret(block_name: str, env_var: str) -> str:
    # Intenta Prefect Block primero
    # Fallback a variable de entorno (.env)
```

**Uso en producción (Prefect Cloud/Blocks):**
```
Prefect Block "supabase-url" → SUPABASE_URL
Prefect Block "supabase-key" → SUPABASE_SERVICE_ROLE_KEY
...
```

**Uso local (.env):**
```
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
```

### 2. Ejecución Local

Ejecutar el flow localmente (para testing):

```bash
# Sin fecha (usa hoy)
python src/flows/valle_frio_bot_flow.py

# Con fecha específica (YYYY-MM-DD)
python src/flows/valle_frio_bot_flow.py 2026-08-14
```

### 3. Deploy en Prefect

Crear 3 deployments automáticos con schedules:

```bash
python deploy.py
```

Esto crea:
- `valle-frio-bot-8am` - Ejecuta a las 8:00 AM (lunes a viernes)
- `valle-frio-bot-12pm` - Ejecuta a las 12:00 PM (lunes a viernes)
- `valle-frio-bot-6pm` - Ejecuta a las 18:00 PM (lunes a viernes)

### 4. Ejecutar Manualmente

```bash
# Ejecutar un deployment específico
prefect deployment run 'valle-frio-bot-8am'

# Ver estado de los deployments
prefect deployment ls

# Ver logs de un deployment
prefect deployment logs 'valle-frio-bot-8am'

# Ver historial de ejecuciones
prefect flow-run ls
```

## Arquitectura del Flow

### ETAPA 0: Nóminas Parciales Pendientes
- Obtiene nóminas con estado "parcial" o "pendiente" de cualquier fecha
- Prepara lista para reintentar en ETAPA 1

### PASO 0: Login
- Inicia sesión en Banco Consorcio

### PASO 1-1.6: Cartola
- **PASO 1**: Descarga cartola del día
- **PASO 1.5**: Procesa cartola para evitar duplicados
- **PASO 1.6**: Sube cartola a Google Drive (si hay movimientos nuevos)

### ETAPA 1: Procesar Nóminas Parciales
- Reintentar hasta 48 nóminas parciales pendientes
- Verificar estado (completada, anulada, pendiente)
- Descargar comprobantes (hasta 48 por nómina)
- Subir a Drive
- Marcar como "completo" en BD

### PASO 2-3.5: Nóminas Nuevas del Día
- **PASO 2**: Descargar nóminas nuevas de la fecha actual
- **PASO 3**: Descargar comprobantes individuales
- **PASO 3.5**: Subir comprobantes a Google Drive
- Actualizar estado en Supabase

## Variables de Entorno Requeridas

```env
# Banco Consorcio
BANCO_USUARIO=20.430.968-K
BANCO_CLAVE=Cons_2108

# Google Drive
GOOGLE_DRIVE_CREDENTIALS_PATH=/ruta/a/credentials.json
DRIVE_FOLDER_ID_CARTOLAS=1wIMazNNEGuCV29kJwHfIgM_HiTFGcF_Z
DRIVE_FOLDER_ID_COMPROBANTES=1kXrCcPI9xflRB0l59tvdd9xy5v2cEVfq
DRIVE_FOLDER_ID_NOMINAS=1ah481Q2iQ2EzlZOgbhyszg18BjprlT4N

# Supabase
SUPABASE_URL=https://zczzcvlpvnwevoxfosdp.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Configuración
BANCO_NOMBRE_CARPETA=consorcio
DOWNLOAD_TEMP_PATH=/ruta/a/temp_downloads
LOG_PATH=/ruta/a/logs
MODO_DRY_RUN=false
```

## Logging

El flow usa `get_run_logger()` de Prefect, que automáticamente:
- Escribe logs en Prefect Cloud/Server
- Permite filtrar y buscar logs por ejecución
- Mantiene historial de ejecuciones

En ejecución local:
```
[17:30:45.123] ✓ Secreto cargado desde .env: BANCO_USUARIO
[17:30:46.456] INICIANDO BOT CONSORCIO (PREFECT FLOW)
...
```

## Diferencias con run.py Original

| Aspecto | run.py | Flow |
|--------|--------|------|
| Punto de entrada | `BotConsorcio.ejecutar()` | `@flow` decorator |
| Logging | `logging.getLogger()` | `get_run_logger()` |
| Secretos | Solo .env | Dual (Blocks + .env) |
| Ejecución | Manual con asyncio | Prefect + scheduling |
| Monitoreo | Archivos locales | Prefect Cloud/UI |
| Parámetros | Línea de comandos | Prefect parameters |
| Recuperación de errores | Manual | Automática en Prefect |

## Instalación

### 1. Instalar Prefect 3.7.5

```bash
pip install prefect==3.7.5
```

O actualizar requirements.txt (ya hecho):
```bash
pip install -r bot1/requirements.txt
```

### 2. Configurar Prefect (si usas Cloud)

```bash
prefect cloud login
```

### 3. Crear Work Pool (Lenovo)

```bash
prefect work-pool create -t process "lenovo-rpa-pool"
prefect work-pool start "lenovo-rpa-pool"
```

## Ejecución en Producción

### Opción 1: En la Lenovo (Recomendado)

```bash
# En la Lenovo, iniciar el work pool agent
prefect agent start "lenovo-rpa-pool"

# Desde el servidor Prefect, ejecutar deploy
python deploy.py

# Los deployments se ejecutarán automáticamente según schedule
```

### Opción 2: Ejecución Manual

```bash
# En cualquier máquina con Python/Prefect instalado
prefect deployment run 'valle-frio-bot-8am'
```

## Monitoreo

### En Prefect Cloud

1. Ir a https://app.prefect.cloud
2. Navegar a "Flows" → "valle-frio-bot-flow"
3. Ver ejecuciones, logs, métricas
4. Configurar alertas si es necesario

### En Local

```bash
prefect flow-run ls  # Ver ejecuciones
prefect flow-run inspect FLOW_RUN_ID  # Detalles de una ejecución
```

## Troubleshooting

### "Flow no carga"

```bash
# Verificar sintaxis
python -m py_compile src/flows/valle_frio_bot_flow.py

# Verificar imports
python -c "from src.flows.valle_frio_bot_flow import valle_frio_bot_flow"
```

### "Secretos no encontrados"

```bash
# Verificar .env existe
cat .env | grep SUPABASE_URL

# Crear Prefect Blocks si es necesario
prefect block register prefect_secrets.EnvironmentVariableSecret --name supabase-url
```

### "Work pool no existe"

```bash
# Crear work pool
prefect work-pool create -t process "lenovo-rpa-pool"

# Iniciar agent
prefect agent start "lenovo-rpa-pool"
```

## Referencias

- [Prefect Documentation](https://docs.prefect.io)
- [Prefect Deployments](https://docs.prefect.io/concepts/deployments/)
- [Prefect Schedules](https://docs.prefect.io/concepts/schedules/)
- [Prefect Work Pools](https://docs.prefect.io/concepts/work-pools/)
