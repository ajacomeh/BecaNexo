param(
    [Parameter(ParameterSetName = 'Comprobar', Mandatory = $true)] [switch]$Comprobar,
    [Parameter(ParameterSetName = 'Ejecutar', Mandatory = $true)] [switch]$Ejecutar,
    [Parameter(ParameterSetName = 'Revisar', Mandatory = $true)] [switch]$Revisar,
    [int]$FuenteId = 1,
    [string]$BaseEsperada = 'becanexo_db'
)

# Tarea programada del rastreo de SIAU. Solo texto ASCII en los mensajes: PowerShell 5.1 lee este archivo como ANSI.
#   -Comprobar : solo lectura; muestra el estado de la programacion de la fuente.
#   -Ejecutar  : lo que lanza la tarea cada hora; solo captura si la ventana de la fuente se cumplio.
#   -Revisar   : solo lectura; ultimas corridas programadas, si la captura esta atrasada y el final del registro local.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$manage = Join-Path $projectRoot 'backend\manage.py'
$carpetaRegistro = Join-Path $env:LOCALAPPDATA 'BecaNexo\rastreo'
$registro = Join-Path $carpetaRegistro 'programador.jsonl'
# La salida de Python es UTF-8: se decodifica asi para no estropear los acentos del resumen.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'

function Leer-JsonComando([string[]]$Argumentos) {
    $salida = & $python $manage @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "El comando de rastreo termino con codigo $LASTEXITCODE." }
    return (($salida -join "`n") | ConvertFrom-Json -ErrorAction Stop)
}

function Hora-Ecuador {
    $zona = [TimeZoneInfo]::FindSystemTimeZoneById('SA Pacific Standard Time')
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $zona).ToString('yyyy-MM-dd HH:mm:ss')
}

function Registrar-Resultado([object]$Resultado) {
    New-Item -ItemType Directory -Path $carpetaRegistro -Force | Out-Null
    $linea = $Resultado | ConvertTo-Json -Compress -Depth 4
    Add-Content -LiteralPath $registro -Value $linea -Encoding UTF8
}

# "No corresponde aun" se registra solo la primera vez de cada dia (latido): la tarea se dispara cada hora.
function Falta-Latido-De-Hoy {
    if (-not (Test-Path -LiteralPath $registro)) { return $true }
    $ultima = Get-Content -LiteralPath $registro -Tail 1 -Encoding UTF8
    $hoy = (Hora-Ecuador).Substring(0, 10)
    return -not ($ultima -and $ultima.Contains("`"fecha_local`":`"$hoy"))
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
    if (-not $estado.activa -or $estado.politica_version -cnotin @('siau-indice/2', 'siau-nacionales/3', 'siau-nacionales/4') -or $estado.aprobada_publicacion_automatica) {
        throw 'La fuente no cumple las condiciones aprobadas para la programacion.'
    }
    if ($Comprobar) {
        $estado | ConvertTo-Json -Depth 4
        if ($estado.ejecuciones_en_curso -ne 0) { exit 4 }
        exit 0
    }
    if ($Revisar) {
        $codigoError = 'REVISION'
        $corridas = Leer-JsonComando -Argumentos @('rastreo', 'corridas-programadas', '--fuente-id', "$FuenteId")
        $corridas | ConvertTo-Json -Depth 6
        "--- registro local (ultimas 5 lineas): $registro ---"
        if (Test-Path -LiteralPath $registro) { Get-Content -LiteralPath $registro -Tail 5 -Encoding UTF8 } else { 'Todavia no hay registro.' }
        if ($corridas.atrasada) { [Console]::Error.WriteLine('ATENCION: la captura esta atrasada; se salto una corrida.'); exit 5 }
        exit 0
    }

    # Una corrida programada interrumpida o en curso la resuelve el comando (la cierra o la omite sin hacer peticiones).
    $codigoError = 'COMANDO_PROGRAMADO'
    $resultados = Leer-JsonComando -Argumentos @('rastreo', 'programado', '--fuente-id', "$FuenteId")
    $codigoError = 'RESPUESTA_INVALIDA'
    $resultado = @($resultados) | Where-Object { $_.fuente_id -eq $FuenteId -or $_.id } | Select-Object -First 1
    if (-not $resultado) { throw 'El comando no devolvio un resultado para la fuente.' }
    $codigo = switch ($resultado.estado) {
        'finalizada' { 0 }
        'no_corresponde_aun' { 0 }
        'parcial' { 3 }
        'fallida' { 1 }
        'omitida' { 4 }
        default { 5 }
    }
    $resumen = $resultado.resumen
    $fila = [ordered]@{
        instante_utc = [DateTime]::UtcNow.ToString('o')
        fecha_local = Hora-Ecuador
        fuente_id = $FuenteId
        ejecucion_id = $resultado.id
        estado = $resultado.estado
        peticiones = if ($resumen) { $resumen.peticiones } else { $null }
        publicaciones_observadas = $resultado.publicaciones_observadas
        versiones_nuevas = $resultado.versiones_nuevas
        candidatos_nuevos = if ($resumen) { $resumen.candidatos_nuevos } else { $null }
        borradores_creados = if ($resumen) { $resumen.borradores_creados } else { $null }
        incidencias = if ($resumen) { $resumen.incidencias_total } else { 0 }
        interrumpidas_cerradas = if ($resultado.interrumpidas_cerradas) { @($resultado.interrumpidas_cerradas).Count } else { 0 }
        proxima_ejecucion = $resultado.proxima_ejecucion
        texto = if ($resumen) { $resumen.texto } else { 'no corresponde aun (ventana de la fuente)' }
        codigo_salida = $codigo
    }
    $codigoError = 'REGISTRO_LOCAL'
    if ($resultado.estado -ne 'no_corresponde_aun' -or (Falta-Latido-De-Hoy)) { Registrar-Resultado $fila }
    $fila | ConvertTo-Json -Compress
    exit $codigo
} catch {
    # No registrar stdout/stderr ni detalles HTTP: pueden contener datos de la fuente.
    $mensaje = "Error $codigoError. Consultar la ejecucion persistida y el registro local."
    if ($Ejecutar) {
        try {
            Registrar-Resultado ([ordered]@{ instante_utc = [DateTime]::UtcNow.ToString('o'); fecha_local = Hora-Ecuador; fuente_id = $FuenteId; estado = 'error_operativo'; error_codigo = $codigoError; texto = "Error operativo $codigoError"; codigo_salida = 2 })
        } catch { $mensaje = 'Fallo la ejecucion programada y no se pudo escribir el registro local.' }
    }
    [Console]::Error.WriteLine($mensaje)
    exit 2
} finally {
    Pop-Location
}
