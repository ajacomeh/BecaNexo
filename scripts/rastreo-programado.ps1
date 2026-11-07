param([switch]$Ejecutar)

$ErrorActionPreference = 'Stop'
if (-not $Ejecutar) {
    Write-Error 'No se ejecutó el rastreo. Use -Ejecutar únicamente tras autorizar la tarea programada y verificar la base configurada.'
    exit 2
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$manage = Join-Path $projectRoot 'backend\manage.py'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $manage)) {
    Write-Error 'Falta el entorno Python o manage.py del proyecto.'
    exit 2
}

Push-Location $projectRoot
try {
    & $python $manage rastreo programado
    $result = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $result
