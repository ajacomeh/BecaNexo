param(
    [string]$Destino = (Join-Path $env:TEMP 'becanexo_restore_test')
)

# Respaldo para ensayos de restauracion aislada (RNF09). No esta conectado a ninguna tarea programada.
# Genera en $Destino: becanexo_db.backup (pg_dump, formato custom), pg_restore-list.txt, documentos\ (copia del
# almacen RASTREO_STORAGE_ROOT) y manifiesto.json con la ruta relativa, el tamano y el SHA-256 de cada documento.
# Solo lee becanexo_db y el almacen real; la contrasena se toma de la configuracion de Django y nunca se imprime.
# Solo texto ASCII en los mensajes: PowerShell 5.1 lee este archivo como ANSI.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$manage = Join-Path $projectRoot 'backend\manage.py'
$destinoCompleto = [IO.Path]::GetFullPath($Destino)
if ($destinoCompleto.StartsWith([IO.Path]::GetFullPath($projectRoot), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'El destino debe quedar fuera del repositorio.'
}
if (Test-Path -LiteralPath $destinoCompleto) { throw 'El destino ya existe; usar una carpeta nueva.' }
New-Item -ItemType Directory -Path $destinoCompleto | Out-Null

$codigo = @'
import hashlib, json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.db.migrations.recorder import MigrationRecorder
destino = Path(os.environ['BECANEXO_RESPALDO_DESTINO'])
bin_pg = Path(r'C:\Program Files\PostgreSQL\16\bin')
db = settings.DATABASES['default']
if db['NAME'] != 'becanexo_db':
    raise SystemExit('Base inesperada; se esperaba becanexo_db.')
entorno = dict(os.environ, PGPASSWORD=db['PASSWORD'] or '')
inicio = datetime.now(timezone.utc)
volcado = destino / 'becanexo_db.backup'
subprocess.run([str(bin_pg / 'pg_dump.exe'), '--format=custom', '--no-owner', '--no-acl', '--host', db['HOST'] or 'localhost',
                '--port', str(db['PORT'] or 5432), '--username', db['USER'], '--file', str(volcado), db['NAME']],
               check=True, env=entorno, capture_output=True)
lista = subprocess.run([str(bin_pg / 'pg_restore.exe'), '--list', str(volcado)], check=True, capture_output=True)
(destino / 'pg_restore-list.txt').write_bytes(lista.stdout)
origen = Path(settings.RASTREO_STORAGE_ROOT)
copia = destino / 'documentos'
shutil.copytree(origen, copia)
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()
archivos = [{'ruta': p.relative_to(copia).as_posix(), 'tamano_bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(copia.rglob('*')) if p.is_file()]
manifiesto = {'creado_utc': inicio.isoformat(), 'base': db['NAME'], 'volcado': volcado.name,
              'volcado_sha256': sha(volcado), 'volcado_bytes': volcado.stat().st_size,
              'migraciones_aplicadas': MigrationRecorder.Migration.objects.count(),
              'documentos': len(archivos), 'archivos': archivos}
(destino / 'manifiesto.json').write_text(json.dumps(manifiesto, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({'destino': str(destino), 'volcado_bytes': manifiesto['volcado_bytes'], 'volcado_sha256': manifiesto['volcado_sha256'],
                  'entradas_pg_restore_list': sum(1 for l in lista.stdout.decode('utf-8', 'replace').splitlines() if l and not l.startswith(';')),
                  'documentos': len(archivos), 'migraciones_aplicadas': manifiesto['migraciones_aplicadas']}))
'@

$env:BECANEXO_RESPALDO_DESTINO = $destinoCompleto
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $python $manage shell -c $codigo
    if ($LASTEXITCODE -ne 0) { throw "El respaldo termino con codigo $LASTEXITCODE." }
} finally {
    Pop-Location
    Remove-Item Env:BECANEXO_RESPALDO_DESTINO -ErrorAction SilentlyContinue
}
