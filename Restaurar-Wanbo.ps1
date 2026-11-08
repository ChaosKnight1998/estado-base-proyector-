param(
    [string]$Serial,
    [string]$Adb = 'adb',
    [string]$PythonExe = 'python',
    [ValidateRange(1, 65535)][int]$AdbPort = 5038,
    [ValidateSet('menu', 'base')][string]$Mode = 'menu',
    [switch]$Apply,
    [switch]$Pause
)
$ErrorActionPreference = 'Stop'
try {
    if (-not $Serial) {
        Write-Host 'Primero conecta el proyector con Android Platform Tools y autoriza esta computadora.'
        $Serial = Read-Host 'Escribe su identificador ADB (el de adb devices)'
    }
    if ($Serial -notmatch '^[A-Za-z0-9_.:\[\]-]+$') { throw 'Identificador ADB invalido.' }
    $arguments = @((Join-Path $PSScriptRoot 'restaurar.py'), '--serial', $Serial,
        '--adb', $Adb, '--port', $AdbPort, '--mode', $Mode)
    & $PythonExe @arguments
    $result = $LASTEXITCODE
    if ($Apply -and $result -eq 0) {
        $confirmation = Read-Host 'Escribe RESTAURAR para aplicar; cualquier otra cosa cancela'
        if ($confirmation -ceq 'RESTAURAR') {
            $applyArguments = $arguments + @('--apply', '--confirm', 'RESTAURAR')
            & $PythonExe @applyArguments
            $result = $LASTEXITCODE
        } else {
            Write-Host 'Cancelado. No se aplico ningun cambio.'
        }
    }
} catch {
    Write-Host ('No se completo: ' + $_.Exception.Message)
    $result = 1
}
if ($Pause) { Read-Host 'Pulsa Enter para cerrar' | Out-Null }
exit $result
