param(
    [Parameter(ParameterSetName = 'Comprobar', Mandatory = $true)] [switch]$Comprobar,
    [Parameter(ParameterSetName = 'Ejecutar', Mandatory = $true)] [switch]$Ejecutar
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz '.venv\Scripts\python.exe'
$manage = Join-Path $raiz 'backend\manage.py'
$mutex = [System.Threading.Mutex]::new($false, 'Local\BecaNexo-Notificaciones-Gmail')
$adquirido = $false
$codigo = 2
$estado = 'error_operativo'
$resumen = $null
$cierre = $null

function Registrar-Resultado([string]$Estado, [int]$Codigo, [object]$Resumen, [object]$Cierre) {
    $carpeta = Join-Path $env:LOCALAPPDATA 'BecaNexo\correo'
    New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
    $registro = [ordered]@{ instante_utc = [DateTime]::UtcNow.ToString('o'); estado = $Estado; codigo_salida = $Codigo }
    if ($null -ne $Resumen) { $registro.resumen = $Resumen }
    if ($null -ne $Cierre) { $registro.avisos_cierre = $Cierre }
    Add-Content -LiteralPath (Join-Path $carpeta 'programador.jsonl') -Value ($registro | ConvertTo-Json -Compress -Depth 3) -Encoding UTF8
}

try {
    try { $adquirido = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $adquirido = $true }
    if (-not $adquirido) { $estado = 'otra_instancia'; $codigo = 4 }
    elseif (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $manage)) {
        $estado = 'entorno_incompleto'
    } else {
        $sonda = @'
import json, os, sys
from datetime import timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.utils import timezone
from notificaciones.models import EntregaCorreo
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    cursor.fetchone()
db_ok = settings.DATABASES['default']['NAME'] == 'becanexo_db'
smtp_ok = (settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
           and bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD))
pendientes = EntregaCorreo.objects.filter(estado='pendiente', proximo_intento_en__lte=timezone.now()).count()
inciertos = EntregaCorreo.objects.filter(estado='enviando', actualizado_en__lt=timezone.now()-timedelta(minutes=30)).count()
print(json.dumps({'base_correcta': db_ok, 'avisos': settings.AVISOS_CORREO_HABILITADOS,
                  'smtp': smtp_ok, 'pendientes': pendientes, 'inciertos': inciertos}))
'@
        Push-Location (Join-Path $raiz 'backend')
        try { $salida = $sonda | & $python - 2>$null; $salidaCodigo = $LASTEXITCODE }
        finally { Pop-Location }
        if ($salidaCodigo -ne 0) { $estado = 'base_no_disponible' }
        else {
            $config = ($salida -join "`n") | ConvertFrom-Json -ErrorAction Stop
            $pendientes = [int]$config.pendientes
            # Avisos de «cierre próximo» de becas favoritas: como máximo una vez por hora (marca en disco, sin consultar
            # la base cada cinco minutos). Un fallo aquí no detiene el correo; queda en el registro.
            if ($Ejecutar -and $config.base_correcta) {
                $marca = Join-Path $env:LOCALAPPDATA 'BecaNexo\correo\avisos_cierre_ultima.txt'
                $toca = -not (Test-Path -LiteralPath $marca) -or ((Get-Date) - (Get-Item -LiteralPath $marca).LastWriteTime).TotalMinutes -ge 60
                if ($toca) {
                    Push-Location (Join-Path $raiz 'backend')
                    try { $salidaCierre = & $python $manage generar_avisos_cierre 2>$null; $codigoCierre = $LASTEXITCODE }
                    catch { $codigoCierre = 1 }
                    finally { Pop-Location }
                    try {
                        if ($codigoCierre -ne 0) { throw 'generacion_fallida' }
                        $cierre = (@($salidaCierre)[-1]) | ConvertFrom-Json -ErrorAction Stop
                        New-Item -ItemType Directory -Path (Split-Path -Parent $marca) -Force | Out-Null
                        Set-Content -LiteralPath $marca -Value ([DateTime]::UtcNow.ToString('o')) -Encoding UTF8
                        $pendientes += [int]$cierre.encolados
                    } catch { $cierre = 'fallido' }
                }
            }
            if (-not $config.base_correcta) { $estado = 'base_inesperada' }
            elseif (-not $config.avisos) { $estado = 'avisos_deshabilitados'; $codigo = 0 }
            elseif (-not $config.smtp) { $estado = 'smtp_no_configurado' }
            elseif ($Comprobar) {
                $estado = 'diagnostico_aprobado'; $codigo = 0
                $resumen = [ordered]@{ pendientes = $config.pendientes; inciertos = $config.inciertos }
            } elseif ($pendientes -eq 0 -and $config.inciertos -eq 0) {
                $estado = 'cola_vacia'; $codigo = 0
            } else {
                $salida = & $python $manage enviar_correos_becas --confirmar-envios --limite 5 2>$null
                if ($LASTEXITCODE -ne 0) { $estado = 'procesador_fallido' }
                else {
                    $texto = ($salida -join "`n").Trim()
                    if ($texto -notmatch "^\{'enviados': (\d+), 'reintentos': (\d+), 'fallidos': (\d+), 'omitidos': (\d+)\}$") {
                        $estado = 'respuesta_inesperada'
                    } else {
                        $resumen = [ordered]@{ enviados = [int]$Matches[1]; reintentos = [int]$Matches[2]; fallidos = [int]$Matches[3]; omitidos = [int]$Matches[4] }
                        $estado = 'procesado'; $codigo = 0
                    }
                }
            }
        }
    }
} catch {
    # No registrar excepciones ni salida del proceso: podrían incluir datos privados.
    $estado = 'error_operativo'; $codigo = 2
} finally {
    if ($adquirido) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

if ($Ejecutar) {
    try { Registrar-Resultado $estado $codigo $resumen $cierre }
    catch { $estado = 'registro_fallido'; $codigo = 2 }
}
@{ estado = $estado; codigo_salida = $codigo; resumen = $resumen } | ConvertTo-Json -Compress -Depth 3
exit $codigo
