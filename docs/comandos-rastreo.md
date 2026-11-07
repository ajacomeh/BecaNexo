# Rastreo manual persistente: bloques 1 y 2

## Bloque 6: descubrimiento y ejecución periódica preparados

La fuente SIAU usa `siau-indice/2` desde la ampliación auditada del 07/11/2026 (revisión de configuración ID 3). El adaptador puede leer el índice oficial y añadir como candidatas hasta 12 fichas HTTPS del mismo dominio cuya ruta sea `/programa-de-becas-nacionales-.../`; admite hasta 24 PDF del mismo dominio bajo `/wp-content/uploads/AAAA/MM/*.pdf`. Cada URL pasa además por robots, DNS público, TLS y los límites de descarga previos. Una candidata detectada no acredita nacionalidad, oferente, vigencia ni documentación: queda para revisión. Otras fuentes y patrones de ruta requieren integración y comprobación independientes. La aprobación automática de publicación permanece deshabilitada.

Comandos operativos **solo tras autorización de escritura para cada acción**. La ampliación auditada y una ejecución manual real (ID 4) ya se realizaron en `becanexo_db`; los ejemplos no son una instrucción para repetirlas:

```powershell
# Verificar primero la base configurada, la fuente y ausencia de ejecuciones activas.
.\.venv\Scripts\python.exe backend/manage.py rastreo publicaciones --fuente-id 1
.\.venv\Scripts\python.exe backend/manage.py rastreo resumen --ejecucion-id 2
# Ampliación de política con auditoría antes/después; no crea publicaciones.
$clavePolitica = [guid]::NewGuid().ToString()
.\.venv\Scripts\python.exe backend/manage.py rastreo habilitar-descubrimiento --actor-id 1 --motivo "Autorizar fichas nacionales del índice SIAU" --clave $clavePolitica
# Frecuencia configurable de 60 a 10080 minutos, con auditoría antes/después.
# El valor actual de SIAU es 1440; no cambiarlo en desarrollo sin autorización.
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

Para Windows 11 se preparó `scripts/rastreo-programado.ps1`. **Estado actual: la tarea `BecaNexo-Rastreo-SIAU` está habilitada.** El primer disparo quedó en cola mientras el portátil funcionaba con batería y la tarea se deshabilitó; un segundo disparo, autorizado tras conectar corriente externa, terminó correctamente con `no_corresponde_aun` por la frecuencia de 1440 minutos, sin nueva ejecución de rastreo. Para sus disparos periódicos deben permanecer Windows encendido, corriente externa y la sesión de `DESKTOP-705DGCE\Lenovo` iniciada; no hace falta abrir el navegador. Queda pendiente observar una ejecución automática real cuando venza la frecuencia. La condición `DisallowStartIfOnBatteries=True` sigue vigente; el registro operativo del Programador continúa desactivado, pero el segundo resultado quedó en el registro local del script y `LastTaskResult=0`. El respaldo conjunto posterior a la ejecución real ID 4 es `D:\Respaldos_BecaNexo\becanexo_pre_programacion_20261107T132831Z_019f6b41`, verificado con 16 referencias. Para comprobaciones inocuas desde la cuenta ejecutora, sin escribir ni descargar:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Comprobar -FuenteId 1 -BaseEsperada becanexo_db
Test-NetConnection siau.senescyt.gob.ec -Port 443
```

`-Comprobar` consulta únicamente la base, política, frecuencia, publicación automática, ejecuciones activas y próxima fecha; no invoca `programado`. La prueba TCP no sustituye la validación HTTP/TLS/robots del descargador. La cuenta de la tarea debe tener acceso a `.venv`, configuración local, PostgreSQL, almacenamiento documental y salida de red; no incluir contraseñas en scripts ni argumentos. La política `RemoteSigned` se aplica solo a ese proceso y puede requerir firma si el archivo tiene marca de Internet. No cambiar la política global para forzar la ejecución.

La tarea habilitada mantiene el programa `powershell.exe`, argumentos `-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Ejecutar -FuenteId 1 -BaseEsperada becanexo_db` e inicio en `D:\Proyectos\BecaNexo`. Está configurada para no iniciar otra instancia ni reintentar automáticamente. El disparador horario solo despierta el proceso: `frecuencia_min` (SIAU: 1440) decide si hay consulta. La tarea no requiere navegador. El script usa Python de `.venv`, rechaza otra base/política o publicación automática habilitada, y deja un registro JSONL sin URLs ni secretos en `%LOCALAPPDATA%\BecaNexo\rastreo\programador.jsonl` de esa cuenta. Código de salida 0: finalizada o todavía no corresponde; 1: fallida; 3: parcial; 4: omitida; 2: error operativo; 5: estado desconocido. Las incidencias completas se consultan en el historial de rastreo. Conservar la cuenta y las credenciales bajo gestión de Windows, no en el repositorio.

Comando de **registro deshabilitado**, ejecutado una sola vez el 07/11/2026. Se conserva como referencia reproducible; **no volver a ejecutarlo mientras exista la tarea**. Usa la cuenta local `DESKTOP-705DGCE\Lenovo`, única comprobada en la preparación; el tipo de inicio `Interactive` requiere que permanezca iniciada la sesión de Windows, aunque el navegador puede estar cerrado. Si se elige otra cuenta o ejecución con sesión cerrada, comprobar sus permisos/red antes de registrar. No sobrescribe una tarea existente:

```powershell
$accion = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "D:\Proyectos\BecaNexo\scripts\rastreo-programado.ps1" -Ejecutar -FuenteId 1 -BaseEsperada becanexo_db' -WorkingDirectory 'D:\Proyectos\BecaNexo'
$disparador = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$ajustes = New-ScheduledTaskSettingsSet -Disable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 0
$principal = New-ScheduledTaskPrincipal -UserId 'DESKTOP-705DGCE\Lenovo' -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'BecaNexo-Rastreo-SIAU' -Action $accion -Trigger $disparador -Settings $ajustes -Principal $principal -Description 'Rastreo SIAU; frecuencia validada por BecaNexo'
```

El registro inicial dejó la tarea deshabilitada; su habilitación posterior se realizó con autorización expresa. No pegar contraseñas en este comando ni volver a registrarla mientras exista.

Pruebas aisladas reproducibles: `.\.venv\Scripts\python.exe backend/manage.py test rastreo.test_periodico --keepdb --verbosity 1`. El ejecutor Django utiliza `test_becanexo_db` y directorios temporales; las fixtures de índice y fichas no representan descubrimientos reales. La consulta real de solo lectura del 06/11/2026 comprobó robots e índice SIAU HTTP 200, sin descargar fichas ni escribir en desarrollo.

Esta sección conserva el procedimiento histórico de los bloques 1 y 2 para la política cerrada de seis URLs. Desde la raíz del proyecto en PowerShell. No hay publicación, usuarios ficticios ni acceso autenticado a PUSAK. `previsualizar_siau` sigue escribiendo únicamente salidas locales ignoradas, sin ORM de rastreo. El descubrimiento está habilitado por política y la programación de Windows fue habilitada en el bloque 8.

La CLI es una operación local de confianza. `--actor-id` **atribuye** la operación; no es autenticación web. Debe corresponder a un administrador activo existente. Para esta verificación el usuario autorizó seleccionar su cuenta por coincidencia exacta de correo: ID 1. No se modificó la cuenta ni se usó su contraseña.

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

## Pruebas automatizadas

```powershell
.\.venv\Scripts\python.exe backend/manage.py test convocatorias.test_siau --keepdb --verbosity 2
.\.venv\Scripts\python.exe backend/manage.py test rastreo --keepdb --verbosity 2
.\.venv\Scripts\python.exe backend/manage.py test usuarios perfiles convocatorias favoritos --keepdb --verbosity 1
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
```

Ejecutar uno después de otro. Los tests de BD verifican explícitamente test_becanexo_db; las pruebas de concurrencia abren una conexión controlada adicional a esa misma base, no ejecutan la suite en paralelo. Los errores de conexión/driver se registran por clase, sin credenciales. La CLI puede salir correctamente aunque el resultado técnico sea fallida/omitida: revisar siempre el campo estado y sus incidencias.
