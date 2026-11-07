param(
    [Parameter(ParameterSetName = 'Comprobar', Mandatory = $true)] [switch]$Comprobar,
    [Parameter(ParameterSetName = 'Ejecutar', Mandatory = $true)] [switch]$Ejecutar,
    [int]$FuenteId = 1,
    [string]$BaseEsperada = 'becanexo_db'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$manage = Join-Path $projectRoot 'backend\manage.py'

function Leer-JsonComando([string[]]$Argumentos) {
    $salida = & $python $manage @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "El comando de rastreo terminó con código $LASTEXITCODE." }
    return (($salida -join "`n") | ConvertFrom-Json -ErrorAction Stop)
}

function Registrar-Resultado([object]$Resultado) {
    $carpeta = Join-Path $env:LOCALAPPDATA 'BecaNexo\rastreo'
    New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
    $registro = Join-Path $carpeta 'programador.jsonl'
    $linea = $Resultado | ConvertTo-Json -Compress -Depth 4
    Add-Content -LiteralPath $registro -Value $linea -Encoding UTF8
}

if ($FuenteId -le 0 -or [string]::IsNullOrWhiteSpace($BaseEsperada)) {
    [Console]::Error.WriteLine('FuenteId y BaseEsperada deben identificar la fuente y la base previstas.')
    exit 2
}
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $manage)) {
    [Console]::Error.WriteLine('Falta el entorno Python o manage.py del proyecto.')
    exit 2
}

Push-Location $projectRoot
try {
    $codigoError = 'CONSULTA_ESTADO'
    $estado = Leer-JsonComando -Argumentos @('rastreo', 'estado-programacion', '--fuente-id', "$FuenteId")
    $codigoError = 'BASE_INESPERADA'
    if ($estado.base -cne $BaseEsperada) { throw "Base inesperada; se esperaba $BaseEsperada." }
    $codigoError = 'CONFIGURACION_INSEGURA'
    if (-not $estado.activa -or $estado.politica_version -cne 'siau-indice/2' -or $estado.aprobada_publicacion_automatica) {
        throw 'La fuente no cumple las condiciones aprobadas para la programación.'
    }
    if ($Comprobar) {
        $estado | ConvertTo-Json -Depth 4
        if ($estado.ejecuciones_en_curso -ne 0) { exit 4 }
        exit 0
    }
    $codigoError = 'EJECUCION_EN_CURSO'
    if ($estado.ejecuciones_en_curso -ne 0) { throw 'Ya existe una ejecución en curso para esta fuente.' }

    $codigoError = 'COMANDO_PROGRAMADO'
    $resultados = Leer-JsonComando -Argumentos @('rastreo', 'programado', '--fuente-id', "$FuenteId")
    $codigoError = 'RESPUESTA_INVALIDA'
    $resultado = @($resultados) | Where-Object { $_.fuente_id -eq $FuenteId -or $_.id } | Select-Object -First 1
    if (-not $resultado) { throw 'El comando no devolvió un resultado para la fuente.' }
    $codigo = switch ($resultado.estado) {
        'finalizada' { 0 }
        'no_corresponde_aun' { 0 }
        'parcial' { 3 }
        'fallida' { 1 }
        'omitida' { 4 }
        default { 5 }
    }
    $registro = [ordered]@{
        instante_utc = [DateTime]::UtcNow.ToString('o')
        fuente_id = $FuenteId
        ejecucion_id = $resultado.id
        estado = $resultado.estado
        publicaciones_observadas = $resultado.publicaciones_observadas
        versiones_nuevas = $resultado.versiones_nuevas
        observaciones_sin_cambios = $resultado.observaciones_sin_cambios
        incidencias = if ($null -eq $resultado.incidencias) { 0 } else { @($resultado.incidencias).Count }
        codigo_salida = $codigo
    }
    $codigoError = 'REGISTRO_LOCAL'
    Registrar-Resultado $registro
    $registro | ConvertTo-Json -Compress
    exit $codigo
} catch {
    # No registrar stdout/stderr ni detalles HTTP: pueden contener datos de la fuente.
    $mensaje = "Error $codigoError. Consultar la ejecución persistida y el registro local."
    if ($Ejecutar) {
        try {
            Registrar-Resultado ([ordered]@{ instante_utc = [DateTime]::UtcNow.ToString('o'); fuente_id = $FuenteId; estado = 'error_operativo'; error_codigo = $codigoError; codigo_salida = 2 })
        } catch { $mensaje = 'Falló la ejecución programada y no se pudo escribir el registro local.' }
    }
    [Console]::Error.WriteLine($mensaje)
    exit 2
} finally {
    Pop-Location
}
