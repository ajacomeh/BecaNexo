param()

# Prepara dos XML para revisión; nunca registra, habilita ni ejecuta la tarea.
$ErrorActionPreference = 'Stop'
$taskName = '\BecaNexo-Rastreo-SIAU'
$projectRoot = Split-Path -Parent $PSScriptRoot
$expectedScript = Join-Path $PSScriptRoot 'rastreo-programado.ps1'
$raw = & schtasks.exe /Query /TN $taskName /XML
if ($LASTEXITCODE -ne 0 -or -not $raw) { throw 'No se pudo leer la tarea existente.' }

$original = New-Object System.Xml.XmlDocument
$original.PreserveWhitespace = $true
$original.LoadXml(($raw -join [Environment]::NewLine))
$proposed = [System.Xml.XmlDocument]$original.CloneNode($true)
$namespace = $proposed.DocumentElement.NamespaceURI
if ($proposed.DocumentElement.LocalName -ne 'Task' -or -not $namespace) {
    throw 'La definición de la tarea no tiene el formato XML esperado.'
}
$names = New-Object System.Xml.XmlNamespaceManager($proposed.NameTable)
$names.AddNamespace('t', $namespace)

$enabled = $proposed.SelectSingleNode('/t:Task/t:Settings/t:Enabled', $names)
$instances = $proposed.SelectSingleNode('/t:Task/t:Settings/t:MultipleInstancesPolicy', $names)
$principal = $proposed.SelectSingleNode('/t:Task/t:Principals/t:Principal/t:UserId', $names)
$logonType = $proposed.SelectSingleNode('/t:Task/t:Principals/t:Principal/t:LogonType', $names)
$command = $proposed.SelectSingleNode('/t:Task/t:Actions/t:Exec/t:Command', $names)
$arguments = $proposed.SelectSingleNode('/t:Task/t:Actions/t:Exec/t:Arguments', $names)
$workingDirectory = $proposed.SelectSingleNode('/t:Task/t:Actions/t:Exec/t:WorkingDirectory', $names)
$hourly = $proposed.SelectSingleNode('/t:Task/t:Triggers/t:TimeTrigger/t:Repetition/t:Interval', $names)
$triggers = $proposed.SelectSingleNode('/t:Task/t:Triggers', $names)
$settings = $proposed.SelectSingleNode('/t:Task/t:Settings', $names)
$checks = [ordered]@{
    deshabilitada = [bool]($enabled -and $enabled.InnerText -eq 'false')
    instancia_unica = [bool]($instances -and $instances.InnerText -eq 'IgnoreNew')
    sesion_interactiva = [bool]($principal -and $principal.InnerText -and $logonType -and $logonType.InnerText -eq 'InteractiveToken')
    comando = [bool]($command -and $command.InnerText -eq 'powershell.exe')
    argumentos = [bool]($arguments -and $arguments.InnerText.Contains($expectedScript) -and
                        $arguments.InnerText.Contains('-Ejecutar -FuenteId 1 -BaseEsperada becanexo_db'))
    directorio = [bool]($workingDirectory -and $workingDirectory.InnerText -eq $projectRoot)
    disparador_horario = [bool]($hourly -and $hourly.InnerText -eq 'PT1H')
    sin_disparador_login = [bool]($triggers -and $triggers.SelectNodes('t:LogonTrigger', $names).Count -eq 0)
}
$failed = @($checks.Keys | Where-Object { -not $checks[$_] })
if ($failed.Count) { throw ('La tarea difiere en: ' + ($failed -join ', ')) }

$login = $proposed.CreateElement('LogonTrigger', $namespace)
$user = $proposed.CreateElement('UserId', $namespace)
$user.InnerText = $principal.InnerText
$delay = $proposed.CreateElement('Delay', $namespace)
$delay.InnerText = 'PT2M'
[void]$login.AppendChild($user)
[void]$login.AppendChild($delay)
[void]$triggers.AppendChild($login)

$start = $proposed.SelectSingleNode('/t:Task/t:Settings/t:StartWhenAvailable', $names)
if (-not $start) {
    $start = $proposed.CreateElement('StartWhenAvailable', $namespace)
    [void]$settings.InsertBefore($start, $enabled)
}
$start.InnerText = 'true'

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$folder = Join-Path $projectRoot ('outputs\rastreo\recuperacion-login-' + $stamp + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
[void](New-Item -ItemType Directory -Path $folder)
$before = Join-Path $folder 'tarea-original.xml'
$after = Join-Path $folder 'tarea-propuesta.xml'
$original.Save($before)
$proposed.Save($after)

@{
    estado = 'propuesta_sin_aplicar'
    tarea = $taskName
    original = $before
    propuesta = $after
    disparadores = @('horario_PT1H', 'inicio_sesion_PT2M')
    habilitada = $false
} | ConvertTo-Json -Compress
