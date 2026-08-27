# Configuración de Variables de Entorno para Prefect Worker

Este documento explica cómo configurar las variables de entorno sensibles que necesitan los bots en el worker de Prefect.

## Variables Sensibles (No en GitHub)

Las siguientes credenciales se leen desde las variables de entorno del sistema del worker y NO están en `prefect.yaml`:

- `BANCO_CLAVE` - Contraseña del banco Consorcio
- `BANCO_USUARIO` - RUT de usuario del banco
- `SUPABASE_SERVICE_ROLE_KEY` - API key de Supabase
- `GAUSSDB_PASSWORD` - Contraseña de la base de datos GaussDB

## Cómo Configurar en Windows (Worker)

Para que el worker de Prefect pueda acceder a estas variables, deben estar configuradas como **variables de entorno del sistema**:

### Opción 1: PowerShell (Permanente)

```powershell
# En PowerShell como Administrador:
[Environment]::SetEnvironmentVariable("BANCO_USUARIO", "20.998.399-0", "Machine")
[Environment]::SetEnvironmentVariable("BANCO_CLAVE", "Cons_2603", "Machine")
[Environment]::SetEnvironmentVariable("SUPABASE_SERVICE_ROLE_KEY", "eyJ...", "Machine")
[Environment]::SetEnvironmentVariable("GAUSSDB_PASSWORD", "Ctas.Corp#2025#", "Machine")
```

### Opción 2: Archivo .env local (No pushear a GitHub)

Si prefieres usar un archivo `.env` local en el worker:

1. Crea `C:\Users\jpmunoz\valle-frio-bot\.env` en el worker
2. Agrega las variables:
   ```
   BANCO_USUARIO=20.998.399-0
   BANCO_CLAVE=Cons_2603
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   GAUSSDB_PASSWORD=Ctas.Corp#2025#
   ```
3. El `python-dotenv` cargará estas variables automáticamente

## Variables No-Sensibles (En prefect.yaml)

El `prefect.yaml` ya contiene las siguientes variables públicas:

- `GOOGLE_DRIVE_CREDENTIALS_PATH` - Ruta relativa al archivo de credenciales
- IDs de carpetas de Drive
- URLs de servicios
- Configuración general (modos, rutas, etc.)

## Archivo de Credenciales de Google Drive

El archivo `credentials.json` contiene las credenciales de servicio de Google Drive:

1. Debe estar en la raíz del proyecto: `C:\Users\jpmunoz\valle-frio-bot\credentials.json`
2. NO debe ser pusheado a GitHub (está en `.gitignore`)
3. El worker debe tener acceso a este archivo

## Cómo Verificar que Todo Funciona

Una vez configuradas las variables:

1. Ejecuta un test del bot en Prefect Cloud
2. Si faltan variables, verás errores como:
   - `TypeError: expected str, bytes or os.PathLike object, not NoneType`
   - Revisa que todas las variables estén configuradas

## Referencias

- [Prefect Environment Variables](https://docs.prefect.io/latest/concepts/deployments/#environment-variables)
- [Python dotenv Documentation](https://github.com/theskumar/python-dotenv)
