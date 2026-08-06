# Script para configurar Windows Task Scheduler
# Ejecuta el bot a las 8:00 y 12:00 todos los días

$taskName = "BotConsorcio-Cartolas"
$scriptPath = "C:\Users\jpmunoz\valle-frio-bot\run_bot.ps1"
$pythonExe = "C:\Users\jpmunoz\AppData\Local\Programs\Python\Python312\python.exe"
$botPath = "C:\Users\jpmunoz\valle-frio-bot"

# Crear script wrapper que activa venv y ejecuta el bot
$runBotScript = @"
cd '$botPath'
& '.\venv\Scripts\Activate.ps1'
python run.py
"@

$runBotScript | Out-File -FilePath $scriptPath -Encoding UTF8

Write-Host "Script de ejecución creado: $scriptPath"

# Crear acción para ejecutar PowerShell
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File '$scriptPath'"

Write-Host "Acción programada creada"

# Crear disparadores para 8:00 y 12:00
$trigger1 = New-ScheduledTaskTrigger -Daily -At 08:00
$trigger2 = New-ScheduledTaskTrigger -Daily -At 12:00

Write-Host "Disparadores creados (8:00 y 12:00)"

# Crear configuración de la tarea
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -RunOnlyIfIdle:$false

# Crear la tarea
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

# Registrar la tarea (eliminar si existe)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Tarea anterior eliminada"
}

# Crear nueva tarea con dos disparadores
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($trigger1, $trigger2) `
    -Settings $settings `
    -Principal $principal `
    -Force

Write-Host "✓ Tarea programada creada: $taskName"
Write-Host "✓ Se ejecutará a las 08:00 y 12:00 todos los días"
Write-Host "`nPuedes verificar en: Administrador de tareas > Biblioteca del Programador de tareas > $taskName"
