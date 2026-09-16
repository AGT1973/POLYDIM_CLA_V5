$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$LogFile = "E:\POLYDIM_EINSOF\nightly_backup_$Timestamp.log"

Function Write-Log($Message) {
    $Time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Time - $Message" | Out-File $LogFile -Append
    Write-Host "$Time - $Message"
}

Write-Log "=== INICIANDO PROTOCOLO DE RESPALDO NOCTURNO (2 AM) ==="

# 1. GIT PUSH PUBLICO
Write-Log "Ejecutando Git Push en E:\POLYDIM_EINSOF..."
Set-Location -Path "E:\POLYDIM_EINSOF"
git push origin main >> $LogFile 2>&1

# Definir Rutas Origen
$SrcPolydim = "E:\POLYDIM_EINSOF"
$SrcGemini = "C:\Users\eluithi\.gemini"
$SrcAgents = "E:\.agents"

# Definir Rutas Destino (D: y I:)
$Dest1_Polydim = "D:\__proyectos 2026\Polydim\POLYDIM_EINSOF_BACKUP_SEP"
$Dest1_Gemini  = "D:\__proyectos 2026\Polydim\GEMINI_BRAIN_BACKUP"
$Dest1_Agents  = "D:\__proyectos 2026\Polydim\AGENTS_BACKUP"

$Dest2_Polydim = "I:\Mi unidad\POLYDIM_EINSOF_BACKUP_SEP"
$Dest2_Gemini  = "I:\Mi unidad\GEMINI_BRAIN_BACKUP"
$Dest2_Agents  = "I:\Mi unidad\AGENTS_BACKUP"

# 2. RESPALDOS A DISCO D:
Write-Log "Sincronizando POLYDIM hacia D:..."
robocopy $SrcPolydim $Dest1_Polydim /MIR /XD .git _HISTORICO __pycache__ node_modules ENTREGA_2026_08* ENTREGA_2026_09_0* /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

Write-Log "Sincronizando Cerebro .gemini hacia D:..."
robocopy $SrcGemini $Dest1_Gemini /MIR /XD brain /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

Write-Log "Sincronizando Skills .agents hacia D:..."
robocopy $SrcAgents $Dest1_Agents /MIR /XD __pycache__ /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

# 3. RESPALDOS A GDRIVE I:
Write-Log "Sincronizando POLYDIM hacia I: (Google Drive)..."
robocopy $SrcPolydim $Dest2_Polydim /MIR /XD .git _HISTORICO __pycache__ node_modules ENTREGA_2026_08* ENTREGA_2026_09_0* /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

Write-Log "Sincronizando Cerebro .gemini hacia I: (Google Drive)..."
robocopy $SrcGemini $Dest2_Gemini /MIR /XD brain /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

Write-Log "Sincronizando Skills .agents hacia I: (Google Drive)..."
robocopy $SrcAgents $Dest2_Agents /MIR /XD __pycache__ /R:1 /W:1 /LOG+:$LogFile /NDL /NFL

Write-Log "=== RESPALDO COMPLETADO EXITOSAMENTE ==="
