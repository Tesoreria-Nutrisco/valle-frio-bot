# Bot 2 - Deployment en Prefect

## Status ✅

**Bot 2 está 100% listo para Prefect**

✅ Código validado y testeado  
✅ Attachments funcionando (comprobantes vía Edge Function)  
✅ Supabase schema valle_frio_bot configurado  
✅ Email con logo Valle Frío  
✅ Matcher Opción D (basado en ID nómina)  
✅ Prefect 3.7.5 instalado  

## Deployment Options

### Opción 1: Ejecución Local (Recomendado para Testing Inmediato)

```bash
# Ejecutar Bot 2 hoy
python bot2_executor.py

# Ejecutar con fecha específica
python bot2_executor.py 2026-08-21

# Con logs completos
python bot2_executor.py 2026-08-21 > logs/bot2_test.log 2>&1
```

### Opción 2: Prefect Flow Local

```bash
# Ejecutar Bot 2 como Prefect flow
python bot2_prefect_flow.py

# Con fecha
python bot2_prefect_flow.py 2026-08-21
```

### Opción 3: Prefect Cloud (Recomendado para Producción)

#### 1. Configurar Prefect Cloud

```bash
# Loguearse en Prefect Cloud
prefect cloud login

# Ingresar tu API Key de Prefect Cloud
# Obtenerla de: https://app.prefect.cloud/account/api-keys
```

#### 2. Crear Work Pool

```bash
# Crear pool para ejecutar en máquina local (Lenovo)
prefect work-pool create -t process "default"
```

#### 3. Desplegar Bot 2

```bash
# Método 1: Usando Python
python -c "
from bot2_prefect_flow import bot2_flow

bot2_flow.deploy(
    name='bot2-test',
    work_pool_name='default',
    tags=['bot2', 'reconciliacion', 'test']
)
"
```

```bash
# Método 2: Usando Prefect CLI (si está disponible)
prefect deployment build bot2_prefect_flow.py:bot2_flow \
  -n "bot2-test" \
  -t "bot2" \
  -t "reconciliacion" \
  -t "test"

prefect deployment apply bot2_prefect_flow.py-bot2_flow-deployment.yaml
```

#### 4. Ejecutar Worker

```bash
# En la máquina Lenovo, iniciar worker
prefect worker start -p "default"
```

#### 5. Ejecutar Bot 2

```bash
# Desde CLI
prefect deployment run "bot2-reconciliation/bot2-test"

# Con parámetro de fecha
prefect deployment run "bot2-reconciliation/bot2-test" --param fecha_prueba=2026-08-21
```

## Monitoreo

### Logs Locales

```bash
# Ver logs de Bot 2
tail -f logs/bot2_reconciliacion.log

# O con PowerShell
Get-Content logs/bot2_reconciliacion.log -Wait
```

### Prefect Dashboard

```bash
# Abrir dashboard local
prefect server start

# O en Cloud: https://app.prefect.cloud
```

## Flujo de Ejecución de Bot 2

```
1. Obtener egresos de Softland
   └─ Últimos 30 días (Consorcio + BCI)
   
2. Descargar cartola bancaria más reciente
   └─ Desde Google Drive
   
3. Para CADA línea de cartola:
   a) Extraer ID nómina de la glosa
   b) Validar ID nómina en Supabase
   c) Descargar nómina Excel
   d) Extraer beneficiarios del Excel
   e) Comparar monto y RUTs
   
4. Para CONFIRMADOS:
   a) Buscar comprobante en Drive
   b) Registrar en Supabase (bot2_pagos_notificados)
   c) Enviar email con comprobante adjunto
   d) Marcar como notificado
   
5. Para NO_CUADRA:
   a) Alertar al desarrollador
   
6. Para SIN_MATCH:
   a) No hacer nada (aparecerá en próxima corrida)
```

## Troubleshooting

### Error: "Cannot connect to GaussDB"

```
Razón: No hay acceso a red de Softland (10.252.0.149:8000)
Solución: Ejecutar Bot 2 en máquina con acceso a red corporativa
```

### Error: "No module named 'bot2'"

```bash
# Asegurar que el directorio está correcto
cd /ruta/a/valle-frio-bot
python bot2_executor.py
```

### Error: Prefect no está instalado

```bash
pip install prefect==3.7.5
```

### Email no llega o sin adjuntos

Verificar:
1. Edge Function `send-email-bot2` en Supabase tiene código correcto
2. Credenciales Gmail en `.env` son válidas
3. Comprobante existe en Drive
4. `DRIVE_FOLDER_ID_COMPROBANTES` es correcto

## Scheduling

Para ejecutar Bot 2 automáticamente (ej: diariamente):

### Con Cron (Linux/Mac)

```bash
# Editar crontab
crontab -e

# Agregar línea para ejecutar a las 6 AM
0 6 * * * cd /ruta/a/valle-frio-bot && python bot2_executor.py
```

### Con Windows Task Scheduler

```powershell
# Crear tarea que ejecute Bot 2 diariamente a las 6 AM
$action = New-ScheduledTaskAction -Execute "python" -Argument "bot2_executor.py" -WorkingDirectory "C:\Users\jpmunoz\valle-frio-bot"
$trigger = New-ScheduledTaskTrigger -Daily -At 6am
Register-ScheduledTask -TaskName "Bot2-Reconciliacion" -Action $action -Trigger $trigger -RunLevel Highest
```

### Con Prefect Cloud

1. Ir a https://app.prefect.cloud
2. Seleccionar deployment "execute_bot2/bot2-test"
3. Click en "Schedule"
4. Configurar horario (ej: 6 AM diariamente)

## Rollback

Si algo sale mal:

```bash
# Eliminar deployment de Prefect
prefect deployment delete "bot2-reconciliation/bot2-test"

# O simplemente pausar
prefect deployment set-schedule "bot2-reconciliation/bot2-test" --schedule "pause"
```

## Próximos Pasos

1. ✅ Confirmar que Bot 2 funciona (test local)
2. 📌 **AHORA:** Elegir opción de deployment (local, flow, o cloud)
3. 🚀 Desplegar según opción elegida
4. 📊 Monitorear primeras ejecuciones
5. 🔄 Escalable a Bot 1 cuando esté listo

## Recursos

- **Prefect Docs:** https://docs.prefect.io/latest/
- **Prefect Cloud:** https://app.prefect.cloud
- **API Docs:** http://localhost:8000/docs (cuando server está corriendo)
