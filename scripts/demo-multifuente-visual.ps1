param([switch]$Smoke)
# Escenario visual efimero: la prueba limpia sus fixtures al salir.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Falta el entorno virtual de BecaNexo.' }
$previousSettings = $env:DJANGO_SETTINGS_MODULE
$previousMode = $env:BECANEXO_DEMO_VISUAL
$previousSmoke = $env:BECANEXO_DEMO_VISUAL_SMOKE
$previousBlas = $env:OPENBLAS_NUM_THREADS
$previousOmp = $env:OMP_NUM_THREADS
Push-Location $repo
try {
    $env:DJANGO_SETTINGS_MODULE = 'config.demo_multifuente_settings'
    $env:BECANEXO_DEMO_VISUAL = '1'
    $env:BECANEXO_DEMO_VISUAL_SMOKE = if ($Smoke) { '1' } else { '0' }
    $env:OPENBLAS_NUM_THREADS = '1'
    $env:OMP_NUM_THREADS = '1'
    & $python 'backend/manage.py' test 'rastreo.test_candidate_transition.CandidateTransitionTests.test_siau_and_generic_portal_keep_private_drafts_and_frequency_separate' --settings=config.demo_multifuente_settings --keepdb --verbosity=1
    if ($LASTEXITCODE -ne 0) { throw "Demostracion visual fallida (codigo $LASTEXITCODE)." }
} finally {
    $env:DJANGO_SETTINGS_MODULE = $previousSettings
    $env:BECANEXO_DEMO_VISUAL = $previousMode
    $env:BECANEXO_DEMO_VISUAL_SMOKE = $previousSmoke
    $env:OPENBLAS_NUM_THREADS = $previousBlas
    $env:OMP_NUM_THREADS = $previousOmp
    Pop-Location
}
