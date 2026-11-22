# Rastreo manual persistente: bloques 1 y 2

## Bloque 6: descubrimiento y ejecución periódica preparados

### Ampliación nacional preparada (bloque 16, etapa 3)

La fuente real pasó de `siau-indice/2` a `siau-nacionales/3` mediante la revisión auditada ID 4 el 10/11/2026. La política conserva el índice y las cuatro fichas históricas, y añade únicamente la primera página HTML de `https://siau.senescyt.gob.ec/portfolio/convocatorias/`. Solo acepta tarjetas de `category-convocatorias` con título de beca nacional y URL HTTPS del mismo dominio; confirma título, fecha de cierre y sección de requisitos en la ficha antes de crear su identidad. Todo pasa por robots, DNS público, TLS y límites existentes. El índice anuncia más páginas mediante AJAX: el rastreador no envía ese POST y registra cobertura **parcial**. Las bases que no sean PDF permitido, como ZIP, quedan pendientes de revisión sin descarga. Una candidata no acredita oferente ecuatoriano, vigencia ni aprobación editorial.

La captura manual única del 11/11/2026 quedó como ejecución ID 6, parcial por cobertura del índice y ZIP fuera del contrato PDF; registró OCCITEC como publicación rastreada, sin crear convocatoria. El script de Windows admite las políticas auditadas `/2` y `/3`, pero mantiene las comprobaciones de base esperada, fuente activa y publicación automática deshabilitada. Su modo `-Comprobar` aprobó bajo `/3`; la tarea existente se rehabilitó sin alterar sus disparadores. No volver a lanzar el ejemplo manual de abajo para esta captura.

Tras autorización expresa, con una cuenta administradora real y sin ejecuciones en curso, la transición auditada e idempotente se solicita desde la raíz con una UUID nueva:

```powershell
$claveNacionales = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo habilitar-nacionales --actor-id <ID_ADMIN_AUTORIZADO> --motivo "Autorizar indice nacional SIAU" --clave $claveNacionales
```

Comprobar después `rastreo estado-programacion --fuente-id 1`. El comando **no ejecuta** rastreo ni cambia la frecuencia; el Programador de Windows seguirá usando el control interno de 1440 minutos. No ejecutar la transición ni una captura real sin autorización y respaldo vigente.

Si una incidencia exige volver exclusivamente a `siau-indice/2`, primero comprobar que no exista ejecución activa ni disparo concurrente del Programador. Con autorización administrativa separada, motivo y UUID nuevos, usar el comando auditado; conserva publicaciones, versiones y documentos:

```powershell
$claveReversion = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo revertir-nacionales --actor-id <ID_ADMIN_AUTORIZADO> --motivo "Revertir política nacional SIAU tras incidencia verificada" --clave $claveReversion
```

Consultar después `rastreo estado-programacion --fuente-id 1` y la revisión de configuración registrada. Este procedimiento queda preparado; **no se ejecutó la reversión en desarrollo**.

La fuente SIAU usó `siau-indice/2` desde la ampliación auditada del 07/11/2026 (revisión de configuración ID 3) hasta la transición del 10/11/2026. El adaptador puede leer el índice oficial y añadir como candidatas hasta 12 fichas HTTPS del mismo dominio; admite hasta 24 PDF del mismo dominio bajo `/wp-content/uploads/AAAA/MM/*.pdf`. Cada URL pasa además por robots, DNS público, TLS y los límites de descarga previos. Una candidata detectada no acredita nacionalidad, oferente, vigencia ni documentación: queda para revisión. Otras fuentes y patrones de ruta requieren integración y comprobación independientes. La aprobación automática de publicación permanece deshabilitada.

Comandos operativos **solo tras autorización de escritura para cada acción**. La ampliación auditada y una ejecución manual real (ID 4) ya se realizaron en `becanexo_db`; los ejemplos no son una instrucción para repetirlas:

```powershell
# Verificar primero la base configurada, la fuente y ausencia de ejecuciones activas.
.\.venv\Scripts\python.exe backend/manage.py rastreo publicaciones --fuente-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo resumen --ejecucion-id 2
# Ampliación de política con auditoría antes/después; no crea publicaciones.
$clavePolitica = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo habilitar-descubrimiento --actor-id 1 --motivo "Autorizar fichas nacionales del índice SIAU" --clave $clavePolitica
# Frecuencia configurable de 60 a 10080 minutos, con auditoría antes/después.
# El valor actual de SIAU es 720 (12 h, mínimo admitido; desde el 22/11/2026); no cambiarlo en desarrollo sin autorización.
$claveFrecuencia = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo configurar-frecuencia --fuente-id 1 --actor-id 1 --motivo "Ajustar periodicidad SIAU" --frecuencia-min 2880 --clave $claveFrecuencia
# Una ejecución manual controlada conserva su clave para reintentos idempotentes.
$claveEjecucion = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo ejecutar --fuente-id 1 --actor-id 1 --clave $claveEjecucion
# Invocación sin actor ficticio; comprueba frecuencia_min y registra ejecuciones debidas.
.\.venv\Scripts\python.exe backend/manage.py rastreo programado --fuente-id 1
```

`configurar-frecuencia` exige administrador activo y motivo, rechaza valores fuera de 60–10080 minutos y registra una revisión inmutable con valores antes/después cuando hay cambio. Si falla la auditoría, la transacción revierte la frecuencia. Repetir la misma clave y contenido no duplica la revisión; un valor igual al actual devuelve `cambio=false`.

La ejecución programada usa `origen=programada`, actor nulo, bloqueo PostgreSQL de origen/fuente e índice único de ejecución activa. Si todavía no vence `frecuencia_min`, responde `no_corresponde_aun` sin nueva petición ni fila. Cuando vence, registra accesos, observaciones sin cambios, nuevas versiones o incidencias y estados `finalizada`, `parcial` o `fallida`. Una interrupción dura exige `rastreo recuperar` con administrador real; no se reutiliza evidencia incompleta como aprobada. La CLI no publica, vincula ni crea convocatorias.

Para Windows 11 se preparó `scripts/rastreo-programado.ps1`. **Estado actual: la tarea `BecaNexo-Rastreo-SIAU` está habilitada.** El primer disparo quedó en cola mientras el portátil funcionaba con batería y la tarea se deshabilitó; un segundo disparo, autorizado tras conectar corriente externa, terminó correctamente con `no_corresponde_aun` por la frecuencia de 1440 minutos, sin nueva ejecución de rastreo. Para sus disparos periódicos deben permanecer Windows encendido, corriente externa y la sesión de `<EQUIPO>\<usuario>` iniciada; no hace falta abrir el navegador. Queda pendiente observar una ejecución automática real cuando venza la frecuencia. Desde el 20/11/2026 `DisallowStartIfOnBatteries` y `StopIfGoingOnBatteries` están en falso; el registro operativo del Programador continúa desactivado, pero el segundo resultado quedó en el registro local del script y `LastTaskResult=0`. El respaldo conjunto posterior a la ejecución real ID 4 es `D:\Respaldos_BecaNexo\becanexo_pre_programacion_20261107T132831Z_019f6b41`, verificado con 16 referencias. Para comprobaciones inocuas desde la cuenta ejecutora, sin escribir ni descargar:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Comprobar -FuenteId 1 -BaseEsperada becanexo_db
Test-NetConnection siau.senescyt.gob.ec -Port 443
```

`-Comprobar` consulta únicamente la base, política, frecuencia, publicación automática, ejecuciones activas y próxima fecha; no invoca `programado`. La prueba TCP no sustituye la validación HTTP/TLS/robots del descargador. La cuenta de la tarea debe tener acceso a `.venv`, configuración local, PostgreSQL, almacenamiento documental y salida de red; no incluir contraseñas en scripts ni argumentos. La política `RemoteSigned` se aplica solo a ese proceso y puede requerir firma si el archivo tiene marca de Internet. No cambiar la política global para forzar la ejecución.

La tarea habilitada mantiene el programa `powershell.exe`, argumentos `-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Ejecutar -FuenteId 1 -BaseEsperada becanexo_db` e inicio en `D:\Proyectos\BecaNexo`. Está configurada para no iniciar otra instancia ni reintentar automáticamente. El disparador horario solo despierta el proceso: `frecuencia_min` (SIAU: 1440) decide si hay consulta. La tarea no requiere navegador. El script usa Python de `.venv`, rechaza otra base/política o publicación automática habilitada, y deja un registro JSONL sin URLs ni secretos en `%LOCALAPPDATA%\BecaNexo\rastreo\programador.jsonl` de esa cuenta. Código de salida 0: finalizada o todavía no corresponde; 1: fallida; 3: parcial; 4: omitida; 2: error operativo; 5: estado desconocido. Las incidencias completas se consultan en el historial de rastreo. Conservar la cuenta y las credenciales bajo gestión de Windows, no en el repositorio.

Comando de **registro deshabilitado**, ejecutado una sola vez el 07/11/2026. Se conserva como referencia reproducible; **no volver a ejecutarlo mientras exista la tarea**. Usa la cuenta local `<EQUIPO>\<usuario>`, única comprobada en la preparación; el tipo de inicio `Interactive` requiere que permanezca iniciada la sesión de Windows, aunque el navegador puede estar cerrado. Si se elige otra cuenta o ejecución con sesión cerrada, comprobar sus permisos/red antes de registrar. No sobrescribe una tarea existente:

```powershell
$accion = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Ejecutar -FuenteId 1 -BaseEsperada becanexo_db' -WorkingDirectory 'D:\Proyectos\BecaNexo'
$disparador = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$ajustes = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 0
$principal = New-ScheduledTaskPrincipal -UserId '<EQUIPO>\<usuario>' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'BecaNexo-Rastreo-SIAU' -Action $accion -Trigger $disparador -Settings $ajustes -Principal $principal -Description 'Rastreo SIAU; frecuencia validada por BecaNexo'
```

El registro inicial dejó la tarea deshabilitada; su habilitación posterior se realizó con autorización expresa. No pegar contraseñas en este comando ni volver a registrarla mientras exista.

Pruebas aisladas reproducibles: `.\.venv\Scripts\python.exe backend/manage.py test rastreo.test_periodico --keepdb --verbosity 1`. El ejecutor Django utiliza `test_becanexo_db` y directorios temporales; las fixtures de índice y fichas no representan descubrimientos reales. La consulta real de solo lectura del 06/11/2026 comprobó robots e índice SIAU HTTP 200, sin descargar fichas ni escribir en desarrollo.

Esta sección conserva el procedimiento histórico de los bloques 1 y 2 para la política cerrada de seis URLs. Desde la raíz del proyecto en PowerShell. No hay publicación, usuarios ficticios ni acceso autenticado a PUSAK. `previsualizar_siau` sigue escribiendo únicamente salidas locales ignoradas, sin ORM de rastreo. El descubrimiento está habilitado por política y la programación de Windows fue habilitada en el bloque 8.

La CLI es una operación local de confianza. `--actor-id` **atribuye** la operación; no es autenticación web. Debe corresponder a un administrador activo existente. Para esta verificación el usuario autorizó seleccionar su cuenta por coincidencia exacta de correo: ID 1. No se modificó la cuenta ni se usó su contraseña.

## Corrida programada: modos, revisión y cierre de interrumpidas

`scripts/rastreo-programado.ps1` tiene tres modos, con `-FuenteId 1 -BaseEsperada becanexo_db` por defecto. Los tres rechazan otra base, una fuente inactiva, una política distinta de `siau-indice/2`, `siau-nacionales/3` o `siau-nacionales/4` y la publicación automática habilitada.

```powershell
# Solo lectura: estado de la programación (base, política, frecuencia, última y próxima ejecución).
# Sale con 4 si hay una ejecución en curso.
powershell -NoProfile -File .\scripts\rastreo-programado.ps1 -Comprobar
# Lo que lanza la tarea cada hora: solo captura si venció la ventana de la fuente.
powershell -NoProfile -File .\scripts\rastreo-programado.ps1 -Ejecutar
# Solo lectura: últimas corridas programadas, atraso y últimas 5 líneas del registro local.
# Sale con 5 si la captura está atrasada.
powershell -NoProfile -File .\scripts\rastreo-programado.ps1 -Revisar
```

`-Revisar` usa el comando de solo lectura `corridas-programadas`, que también puede consultarse directamente:

```powershell
.\.venv\Scripts\python.exe backend\manage.py rastreo corridas-programadas --fuente-id 1
```

Devuelve `proxima_ejecucion`, `atrasada` (verdadero cuando pasaron más de 2 horas desde la hora prevista), `horas_de_atraso`, la última captura que no fue omitida y el resumen de las 10 últimas corridas programadas.

**Cierre automático de interrumpidas.** Antes de cada corrida programada, con la exclusión de la fuente ya obtenida, se cierran como `fallida` las corridas programadas que siguen «en curso» sin latido en los últimos 10 minutos (`INTERRUMPIDA_MINUTOS`), con la incidencia `INTERRUMPIDA`. Un proceso vivo conservaría la exclusión, así que lo que sigue en curso ya no tiene proceso. Solo afecta a corridas programadas, sin actor; las manuales siguen exigiendo `recuperar`. La corrida cerrada consume la ventana de frecuencia.

**Resumen de cada corrida.** El resultado de `programado` y de `resumen` incluye `resumen` con `peticiones`, `publicaciones_observadas`, `versiones_nuevas`, `candidatos_nuevos`, `borradores_creados`, `incidencias_total`, `incidencias_por_codigo`, `motivo` (en corridas omitidas o fallidas) y un `texto` legible. El script guarda una línea por corrida en `%LOCALAPPDATA%\BecaNexo\rastreo\programador.jsonl`; el resultado «no corresponde aún» se registra solo una vez por día. Códigos de salida de `-Ejecutar`: 0 finalizada o todavía no corresponde, 1 fallida, 3 parcial, 4 omitida, 2 error operativo y 5 estado desconocido.

**Acción recomendada de la tarea (ventana oculta).** Programa `powershell.exe`, directorio de trabajo `D:\Proyectos\BecaNexo` y argumentos:

```powershell
powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Ejecutar -FuenteId 1 -BaseEsperada becanexo_db
```

**Advertencia:** cerrar la ventana de una corrida en curso la termina con el código `0xC000013A` (`STATUS_CONTROL_C_EXIT`). La ejecución queda «en curso» en la base, sin latido, hasta que el siguiente disparo la cierra como interrumpida; esa corrida cerrada consume la ventana de 12 horas, así que no habrá otra captura hasta que venza.

**Limitaciones conocidas de la corrida programada:**

- El disparador de inicio de sesión puede lanzar la corrida justo al reanudar el equipo, cuando el sistema aún no terminó de estabilizarse.
- Una corrida interrumpida cuenta como captura de la ventana de 12 horas, aunque no haya hecho ninguna petición.
- La tarea solo corre con la sesión de Windows abierta y el equipo despierto; los disparos perdidos durante la suspensión se recuperan únicamente por `StartWhenAvailable`.

## Política vigente siau-nacionales/4 (desde el 22/11/2026)

La ejecución programada 14 (22/11/2026) terminó parcial con dos incidencias, cuya causa se diagnosticó en solo lectura:

- **`INDICE_LIMITE`:** con `siau-nacionales/3` el índice nacional (`/portfolio/convocatorias/`) solo admitía tarjetas cuyo título dijera «becas nacionales» y no seguía la paginación AJAX que anuncia la página (`max_num_pages` = 3). La primera página tenía 19 tarjetas con «beca» y solo una con «becas nacionales»; por eso «Programa de Becas para Mujeres Ecuatorianas Universidad Europea» dejó de observarse.
- **`BASE_NO_PERMITIDA` (publicación 5, OCCITEC):** las bases son un ZIP del propio SIAU (`/wp-content/uploads/2026/10/2026-0494.zip`). No es robots.txt: la regla `BASE` solo admite archivos `.pdf` en `/wp-content/uploads/AAAA/MM/` de `siau.senescyt.gob.ec`. Por decisión del responsable, el ZIP queda como base pendiente de revisión manual (`fuera_de_lista`), sin descarga.

La fuente pasó a `siau-nacionales/4` con el comando auditado `rastreo habilitar-paginacion` (actor 1). Esta política admite cualquier tarjeta del índice con «beca» en el título y sigue la paginación AJAX solo si robots.txt permite `/wp-admin/admin-ajax.php` (hoy lo permite). Las fichas siguen el mismo clasificador: lo que no acredita oferente ecuatoriano queda pendiente o descartado y nada se publica solo.

| Límite | Valor | Qué cuenta |
| --- | ---: | --- |
| `MAX_FICHAS` (`rastreo/descubrimiento.py`) | 12 | Fichas procesadas por corrida. Primero las no vistas y luego las vistas hace más tiempo, así que el índice completo se cubre por rotación en varias corridas. |
| `MAX_INDEX_PAGES` (`rastreo/siau_ajax.py`) | 12 | Tope de seguridad de páginas AJAX. Cada corrida consulta una página adicional y avanza un cursor. |
| `MAX_BASES` (`rastreo/descubrimiento.py`) | 24 | PDF de bases descargados por corrida. |

**Frecuencia de 12 horas (22/11/2026).** El piso está en el código: `FRECUENCIA_MINIMA_MIN` = 720 (`rastreo/models.py`, migración `0015`), y `set_frequency` solo admite de 720 a 10080 minutos. La fuente SIAU pasó de 1440 a 720 con el comando auditado `rastreo configurar-frecuencia --frecuencia-min 720` (actor 1). La tarea programada y el botón «Iniciar rastreo» del panel usan la misma ventana (`next_due`): inicio de la última captura no omitida + `frecuencia_min`. «Próxima disponibilidad» se calcula igual. La tarea `BecaNexo-Rastreo-SIAU` no se volvió a registrar: ya se dispara cada hora (minuto :46), al iniciar sesión (con 2 min de retraso) y con «ejecutar lo antes posible si se perdió el inicio». Cada disparo antes de la ventana devuelve «no corresponde aún» sin crear ejecuciones (solo una línea diaria en el registro local), así que el disparo horario no genera ruido en la lista.

Para volver a la política anterior: `rastreo revertir-paginacion --actor-id <ID> --motivo "<motivo>" --clave <UUID>`. El script de la tarea programada acepta `/2`, `/3` y `/4`.

## Configuración y comandos

Consultas nuevas del bloque 2, **sin red y sin escrituras** (sustituir IDs por los listados):

```powershell
.\.venv\Scripts\python.exe backend/manage.py rastreo publicaciones --fuente-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo versiones --publicacion-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo documentos --version-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo observaciones --ejecucion-id 2
# Comparación solo entre versiones de la misma publicación; admite comparar una consigo misma.
.\.venv\Scripts\python.exe backend/manage.py rastreo diferencias --version-id 1 --otra-version-id 1
```

`versiones` incluye manifiesto, huellas, número, extractor/normalizador/contrato y advertencias; `documentos` muestra referencias exactas, no interpreta ni aprueba el PDF. `diferencias` muestra campos pertinentes antes/después y ambos manifiestos/extractores; no calcula similitud ni propone aplicar cambios. IDs inexistentes o versiones de distintas publicaciones se rechazan. Listados sin paginación en esta CLI local acotada a dos fichas; no es API pública.

`resumen` ahora expone `publicaciones_observadas`, `versiones_nuevas`, `observaciones_sin_cambios` y `convocatorias_creadas: 0`. Se retira el ambiguo `publicaciones_creadas: 0` del bloque 1. Una falla conocida cuenta como observación con versión NULL; una ficha inicialmente desconocida que no logra conservar HTML no fabrica identidad/versión. La ejecución 1 conserva contadores cero y no recibe observaciones retrospectivas.

Una misma evidencia/contrato reutiliza versión, pero deja observación y accesos nuevos. Cambio solo decorativo produce otra versión con igual huella relevante; PDF distinto siempre cambia manifiesto. Bases inaccesibles permanecen pendientes sin reemplazo por las antiguas. Revisión documental y publicación siguen deshabilitadas en este bloque.

Estado real comprobado el 28/10/2026: ejecución **2**, UUID `aefd2102-e4a0-4651-8175-a73eb673df0b`, finalizada; publicaciones 1/2, versiones 1/2 (número 1), observaciones 1/2, cuatro relaciones documentales. Jóvenes es publicación 1 y Productivo publicación 2. Seis accesos HTTP 200, avisos 3/4 de revisión documental pendiente. Nueve documentos totales íntegros. No lanzar `ejecutar` para consultar estos resultados:

```powershell
.\.venv\Scripts\python.exe backend/manage.py showmigrations rastreo
.\.venv\Scripts\python.exe backend/manage.py migrate --plan
.\.venv\Scripts\python.exe backend/manage.py rastreo resumen --ejecucion-id 2
.\.venv\Scripts\python.exe backend/manage.py rastreo publicaciones --fuente-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo versiones --publicacion-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo versiones --publicacion-id 2
.\.venv\Scripts\python.exe backend/manage.py rastreo documentos --version-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo documentos --version-id 2
.\.venv\Scripts\python.exe backend/manage.py rastreo observaciones --ejecucion-id 2
.\.venv\Scripts\python.exe backend/manage.py rastreo observaciones --ejecucion-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo integridad
```

La consulta de observaciones de la ejecución 1 devuelve `[]`: su extracción no se reconstruyó retrospectivamente. Solo existe una versión por publicación; no hay todavía un par real diferente de la misma identidad para comparar. Los cambios A→B→A y de PDF están cubiertos por pruebas sintéticas.

`backend/.env` contiene `RASTREO_STORAGE_ROOT=D:/Datos_BecaNexo/rastreo`. Se comprobó esa carpeta real, sin confusión con «rastro». No se sirve mediante MEDIA_URL. Pruebas usan TemporaryDirectory separado; nunca la carpeta real.

```powershell
# Registro inicial desactivado; repetir no duplica ni sobrescribe configuración.
.\.venv\Scripts\python.exe backend/manage.py rastreo configurar --actor-id 1 --motivo "Alta inicial SIAU"

# Usar fuente_id devuelto por configurar.
.\.venv\Scripts\python.exe backend/manage.py rastreo activar --actor-id 1 --motivo "Habilitar investigación pública SIAU"

# Guardar la clave: repetirla devuelve la ejecución previa sin otra descarga.
$rastreoClave = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo ejecutar --fuente-id 1 --actor-id 1 --clave $rastreoClave

.\.venv\Scripts\python.exe backend/manage.py rastreo resumen --ejecucion-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo integridad

.\.venv\Scripts\python.exe backend/manage.py rastreo desactivar --actor-id 1 --motivo "Pausar futuras consultas"
# Solo si quedó una ejecución en_curso tras interrupción:
.\.venv\Scripts\python.exe backend/manage.py rastreo recuperar --fuente-id 1 --actor-id 1 --motivo "Recuperación local tras interrupción"
```

Los IDs de ejemplo deben coincidir con los resultados locales documentados en avance.md. Configurar/activar/desactivar admiten `--clave UUID` para idempotencia de acción; una clave reutilizada con distinto actor/motivo/estado se rechaza. Configurar verifica el contrato cerrado de SIAU; no sobrescribe una política existente distinta. No existe argumento para habilitar publicación automática: una restricción PostgreSQL la mantiene false.

Desactivar impide **nuevas** ejecuciones; no cancela una operación ya iniciada. Para interrumpir el proceso se utiliza su terminal; después se puede recuperar bajo exclusión. Una fuente inactiva produce ejecución omitida con motivo, sin DNS/HTTP. Un mismo UUID de ejecución no vuelve a ejecutar aunque su resultado anterior sea omitida/fallida; una investigación nueva requiere otro UUID.

## Historial, concurrencia y fallos

- Bloqueos asesores de sesión, orden origen SIAU → fuente; compartidos por ejecución y recuperación. No hay transacciones abiertas durante DNS, HTTP ni preparación/hash/escritura de documentos. Transacciones cortas para metadatos/accesos y auditoría.
- Creación bajo bloqueo de fila de fuente y clave UUID única; otra invocación sin exclusión queda omitida. Otro proceso con la misma clave devuelve el registro en curso o terminado, sin red. Solo una fila en_curso por fuente por índice parcial.
- KeyboardInterrupt/caída dura puede dejar en_curso. No se considera abandonada por antigüedad. Recuperar exige obtener ambos bloqueos; rechaza trabajador vivo. Registra incidencia y revisión con administrador real, cierra fallida, conserva accesos y documentos. La pérdida de sesión PostgreSQL libera sus locks; no se fuerza un unlock ajeno.
- Cada intento/salto deja acceso, incluidos robots, HTTP fallido y reintentos. Resultado redirigido no tiene documento; descargado/reutilizado sí. Estado finalizada significa finalización técnica, **no** aprobación editorial. Las bases descargadas generan aviso de revisión documental pendiente. Cambio de huella PDF genera otro aviso, sin modificar ofertas.
- Contadores de publicaciones/versiones/observaciones de negocio se mantienen en cero y tienen CHECK; esas estructuras todavía no existen. Los accesos y documentos se cuentan al consultar el resumen.
- Triggers PostgreSQL rechazan UPDATE/DELETE del historial incluso con QuerySet.update/bulk_update; ejecuciones terminales inmutables. Configuración requiere revisión antes/después en la misma transacción, verificada al commit. No se registraron formularios genéricos de estas tablas en Admin.

## Archivos

Clave generada `xx/<sha256>.bin`, dentro de raíz privada. MIME, firma PDF, límites, UTF-8 para texto, tamaño y hash se validan. Bytes idénticos se reutilizan, registrando cada acceso. Archivo diferente/corrupto no se reemplaza. Temporal exclusivo en el mismo volumen, fsync y enlace duro final atómico sin reemplazo; se retira solo el temporal propio tras finalizar, nunca documentos previos. Si falla, temporales/huérfanos quedan para inspección. Requiere un sistema de archivos con enlaces duros (la ruta local prevista es NTFS); no se degrada a copia no atómica.

`integridad` detecta referencias ausentes/corruptas, claves inválidas y archivos sin referencia, devolviendo eliminados=0. No limpia ni repara automáticamente. Archivo guardado y transacción abortada puede dejar huérfano: se informa; nunca se confirma referencia a un archivo cuya escritura falló. Respaldo PostgreSQL **no incluye** bytes; ver [respaldo-rastreo.md](respaldo-rastreo.md).

## Consulta del estado guardado (solo lectura)

Resultados reales confirmados: fuente 1 activa y aprobación automática false; ejecución 1 finalizada, clave `7851d780-f5f3-4b60-9599-afb38db1d955`; seis accesos HTTP 200, seis documentos y dos avisos `REVISION_DOCUMENTAL_PENDIENTE`. No volver a registrar, activar ni descargar para consultar esta evidencia.

```powershell
# Fuente, sin configuración privada ni datos de cuentas.
.\.venv\Scripts\python.exe backend/manage.py shell -v 0 -c "from rastreo.models import Fuente; print(list(Fuente.objects.filter(pk=1).values('id','nombre','url_base','activa','aprobada_publicacion_automatica')))"
# Ejecución e incidencias resumidas.
.\.venv\Scripts\python.exe backend/manage.py rastreo resumen --ejecucion-id 1
# Cada acceso, sin imprimir contenido HTML/PDF.
.\.venv\Scripts\python.exe backend/manage.py shell -v 0 -c "from rastreo.models import Acceso; print(list(Acceso.objects.filter(ejecucion_id=1).order_by('secuencia').values('id','secuencia','rol','http_status','resultado','documento_id','inicio_peticion_en','fin')))"
# Metadatos documentales de esta ejecución; SHA corresponde a archivos públicos, no contraseñas.
.\.venv\Scripts\python.exe backend/manage.py shell -v 0 -c "from rastreo.models import Documento,Acceso; print(list(Documento.objects.filter(id__in=Acceso.objects.filter(ejecucion_id=1).values('documento_id')).values('id','sha256','tamano_bytes','mime','clave_almacenamiento')))"
# Avisos y errores; los avisos pendientes NO son aprobaciones.
.\.venv\Scripts\python.exe backend/manage.py shell -v 0 -c "from rastreo.models import Incidencia; print(list(Incidencia.objects.filter(ejecucion_id=1).values('id','codigo','gravedad','detalle','acceso_id')))"
# Detectar en_curso sin cerrarlas; recuperar es otra operación explícita.
.\.venv\Scripts\python.exe backend/manage.py shell -v 0 -c "from rastreo.models import Ejecucion; print(list(Ejecucion.objects.filter(estado='en_curso').values('id','fuente_id','inicio','latido_en')))"
.\.venv\Scripts\python.exe backend/manage.py rastreo integridad
```

## Candidata PUCE Ambato: preparacion sin activacion

Estado de las fuentes al 14/11/2026: SIAU usa `/3` con 1440 minutos; `/4` permanece inactiva. UTPL conserva el conector pero robots.txt devuelve 403 y requiere aclarar acceso y reutilizacion. UPS conserva el conector y robots.txt no excluye rutas, pero sus condiciones institucionales requieren aclarar la retencion/reutilizacion de contenido. Universidad de las Artes conserva el parser generico; robots.txt excluye `/sitio/download/`, por lo que un futuro registro debe omitir esas descargas y confirmar condiciones de uso. Ninguna de estas fuentes institucionales tiene registro activo en desarrollo. Cada alta o activacion exige actor administrador, motivo auditado, UUID distinta y autorizacion operativa individual.

El indice `https://www.pucesa.edu.ec/financiamiento-y-becas/becas/` permite lectura tecnica segun su robots.txt consultado el 14/11/2026. No se encontro una autorizacion especifica para conservar y reutilizar automaticamente el contenido de ese indice; una politica publicada en otro subdominio de PUCE Ambato no se atribuye a esta pagina. Mantener la fuente sin registrar hasta aclarar esta condicion o acordar un contrato de metadatos y enlaces que el motor pueda cumplir. HTTP 200 no justifica `--acceso-verificado`.

Tras obtener la autorizacion institucional y una autorizacion operativa separada para BecaNexo, el registro inactivo previsto es `rastreo registrar-portal-generico` con `--nombre "PUCE Ambato"`, `--indice "https://www.pucesa.edu.ec/financiamiento-y-becas/becas/"`, `--host www.pucesa.edu.ec`, `--max-paginas 1`, `--max-profundidad 0`, `--max-fichas 4`, actor administrador, motivo documentado y UUID nueva. El servicio establece 1440 minutos y `activa=False`. Verificar despues el acceso mediante `verificar-portal-generico`; `activar-portal` y una unica ejecucion ordinaria requieren autorizacion posterior. La fecha general de inicio del 01/12/2026 para estudiantes nuevos de Grado y PUCETEC no se aplica a las fichas individuales sin evidencia de su alcance.

## Pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe backend/manage.py test convocatorias.test_siau --keepdb --verbosity 2
.\.venv\Scripts\python.exe backend/manage.py test rastreo --keepdb --verbosity 2
.\.venv\Scripts\python.exe backend/manage.py test usuarios perfiles convocatorias favoritos --keepdb --verbosity 1
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
```

Ejecutar uno después de otro. Los tests de BD verifican explícitamente test_becanexo_db; las pruebas de concurrencia abren una conexión controlada adicional a esa misma base, no ejecutan la suite en paralelo. Los errores de conexión/driver se registran por clase, sin credenciales. La CLI puede salir correctamente aunque el resultado técnico sea fallida/omitida: revisar siempre el campo estado y sus incidencias.
