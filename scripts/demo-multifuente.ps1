# Ensayo efimero con HTTP y PDF sinteticos. Nunca consulta fuentes externas.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Falta el entorno virtual de BecaNexo.' }

Push-Location $repo
try {
@'
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, 'backend')
import django
django.setup()
from django.conf import settings
from django.core.management import execute_from_command_line

settings.DATABASES['default']['TEST']['NAME'] = 'test_becanexo_fusion_db'
if settings.DATABASES['default']['TEST']['NAME'] == settings.DATABASES['default']['NAME']:
    raise SystemExit('La base aislada coincide con la base principal; ensayo cancelado.')
execute_from_command_line([
    'manage.py', 'test',
    'rastreo.test_candidate_transition.CandidateTransitionTests.test_siau_and_generic_portal_keep_private_drafts_and_frequency_separate',
    '--keepdb', '--verbosity=1',
])
'@ | & $python -
if ($LASTEXITCODE -ne 0) { throw "Ensayo multifuente fallido (codigo $LASTEXITCODE)." }
} finally {
    Pop-Location
}
