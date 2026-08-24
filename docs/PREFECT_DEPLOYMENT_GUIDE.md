# Deployment de Bot 2 en Prefect

## Status Actual

✅ **Bot 2 está listo para Prefect**
- Código validado y testeado
- Attachments verificados 100%
- Supabase schema configurado
- Email con logo y comprobantes

## Instalación de Prefect

### Opción 1: Instalación Local (Recomendado para Testing)

```bash
pip install prefect==3.7.5
```

### Opción 2: Prefect Cloud (Para Producción)

Requiere API Key. Configurar en `.env`:

```
PREFECT_API_KEY=xxxx
PREFECT_ACCOUNT_ID=xxxx
PREFECT_WORKSPACE_NAME=valle-frio-bot
```

## Ejecución

### Modo Test Local (Sin Prefect Cloud)

```bash
# Ejecutar Bot 2 directamente hoy
python bot2_executor.py

# Ejecutar con fecha específica
python bot2_executor.py 2026-08-21

# Con logs completos
python bot2_executor.py 2026-08-21 2>&1 | Tee-Object -FilePath bot2_test.log
```

### Modo Prefect (Con Scheduling)

#### 1. Inicializar Prefect Cloud (opcional)

```bash
prefect cloud login
# Ingresar tu API Key de Prefect Cloud
```

#### 2. Crear Deployment

```bash
prefect deployment build bot2_executor.py:execute_bot2 \
  --name "bot2-test" \
  --tag "bot2" \
  --tag "reconciliacion" \
  --tag "test"
```

#### 3. Desplegar

```bash
prefect deployment apply bot2_executor.py-execute_bot2-deployment.yaml
```

#### 4. Iniciar Scheduler (si usas Prefect Cloud)

```bash
prefect agent start --pool default
```

#### 5. Ejecutar Manualmente

```bash
# Desde CLI
prefect deployment run "execute_bot2/bot2-test"

# Con parámetros
prefect deployment run "execute_bot2/bot2-test" --param fecha_prueba=2026-08-21
```

## Monitoreo

### Ver logs locales

```bash
# Bot 2 guarda logs en:
tail -f logs/bot2_reconciliacion.log

# O desde PowerShell:
Get-Content logs/bot2_reconciliacion.log -Wait
```

### Ver en Prefect UI

```bash
# Si usas Prefect Cloud, abre:
https://app.prefect.cloud

# Busca deployment: execute_bot2/bot2-test
# Ver histórico de runs, logs, resultados
```

## Validación Pre-Deployment

✅ **Verificaciones completadas:**

- [x] notificador.py adjunta comprobantes correctamente
- [x] Edge Function Supabase recibe attachments
- [x] Nodemailer está configurado para enviar adjuntos
- [x] Bot 1 login funciona (sin selección manual de Valle Frío)
- [x] Supabase schema valle_frio_bot configurado
- [x] RLS y permissions configuradas
- [x] Email template con logo Valle Frío
- [x] Matcher Opción D (basado en ID nómina)

## Flujo de Ejecución

1. **Bot 2 inicia** → obtiene egresos Softland
2. **Descarga cartola** → más reciente de Drive
3. **Matching** → compara montos + ID nómina
4. **Para confirmados:**
   - Busca comprobante en Drive
   - Registra en Supabase
   - Envía email con comprobante adjunto
   - Marca como notificado
5. **Para no_cuadra:** Alerta al desarrollador
6. **Para sin_match:** No hace nada (aparecerá después)

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'prefect'"

```bash
pip install prefect==3.7.5
```

### Error: "Faltan credenciales Supabase"

- Verificar `.env` tiene `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`
- La credencial debe ser `service_role`, no `anon`

### Error: "Connection refused"

- Verificar que GaussDB está accesible en `10.252.0.149:8000`
- Verificar que Supabase URL es accesible
- Verificar que Google Drive credentials están en `credentials.json`

### Email no llega / sin adjuntos

- Verificar Edge Function `send-email-bot2` en Supabase
- Verificar que `GMAIL_BOT2` credenciales son válidas
- Verificar que comprobante existe en Drive

## Rollback

Si algo falla en producción:

```bash
# Eliminar deployment
prefect deployment delete "execute_bot2/bot2-test"

# O simplemente no ejecutar (pausar scheduling)
prefect deployment set-schedule "execute_bot2/bot2-test" --schedule "pause"
```

## Próximos Pasos

1. ✅ Confirmar que Bot 2 se ejecutó exitosamente en test
2. 🔄 Deploy a Prefect (elegir Cloud o Local)
3. 🎯 Configurar scheduling (ej: diariamente a las 6 AM)
4. 📊 Monitorear logs y resultados en Prefect UI
5. 🚀 Escalar a Bot 1 cuando esté listo
