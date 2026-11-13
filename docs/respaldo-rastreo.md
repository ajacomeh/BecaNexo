# Respaldo conjunto de PostgreSQL y documentos

## Copia previa a rastreo.0013 y convocatorias.0006/0007 — 12/11/2026

Respaldo nuevo: `D:\Respaldos_BecaNexo\becanexo_pre_migracion_b18_20261113T001611Z_8f098cd9` (marca UTC; 12/11/2026 en Ecuador). Contiene `becanexo_db.backup` (300907 bytes), `documentos/` (35 archivos), `manifiesto.json`, `pg_restore-list.txt` y `SHA256SUMS.txt`. La captura usó snapshot PostgreSQL exportado y exclusión del rastreador. Se cotejaron tamaño y SHA-256 del dump, de los 35 archivos copiados y de las 35 referencias con los originales; `pg_restore --list` terminó con código 0 y coincidió con el listado guardado. El manifiesto identifica el commit `a269fcd3c289b9c87ee25101a1bf2c36ee44d8e3`, migraciones aplicadas, política `/3`, frecuencia y configuración no secreta. No se ensayó una restauración completa.

Al capturar, desarrollo conservaba 8 convocatorias, 8 favoritos, 5 publicaciones, 20 versiones, 35 documentos y 38 relaciones documentales, sin ejecuciones activas. Las versiones 16–20 y los documentos 29–35 proceden de la ejecución programada ID 7 del 12/11/2026 a las 14:46 de Ecuador: dos HTML de índice y cinco fichas. Las observaciones fueron `cambio_bytes`, sin prueba de cambio sustancial. La tarea Windows permanecía deshabilitada y no había servidor Django `runserver`. `rastreo.0013`, `convocatorias.0006` y `0007` seguían sin aplicar.

**Recuperación segura, solo si se autoriza por separado:** conservar intactos este respaldo y el desarrollo actual; preparar una base PostgreSQL nueva y vacía y una raíz documental nueva, ambas aisladas. Verificar primero `SHA256SUMS.txt`, el manifiesto y `pg_restore --list`. Restaurar el dump en la base aislada con `pg_restore --no-owner --no-acl -d <base_aislada> becanexo_db.backup`, sin `--clean` ni restaurar sobre `becanexo_db`; copiar `documentos/` a la raíz documental aislada. Configurar credenciales por un medio privado, `DB_NAME` para esa base y `RASTREO_STORAGE_ROOT` para esa raíz. Usar una copia separada del código del commit indicado, compatible con el esquema anterior a las tres migraciones; el árbol de trabajo integrado actual no debe arrancarse contra el esquema restaurado sin migrarlo. Mantener Programador, rastreo y publicación automática detenidos; comprobar tablas, migraciones, 35 huellas documentales y relaciones mediante consultas de lectura y `rastreo integridad`. Una restauración completa solo podrá declararse probada después de ejecutar y verificar este ensayo aislado.

## Revisión administrativa — 29/10/2026

Copia nueva previa a rastreo.0006/0007: `D:\Respaldos_BecaNexo\becanexo_pre_revisiones_20261029T103140Z_bd8aa7ea`.

Contiene becanexo_db.backup (210545 bytes), documentos/, manifiesto.json y pg_restore-list.txt. pg_dump con snapshot PostgreSQL exportado y exclusión del rastreo durante captura; metadatos documentales leídos desde el mismo snapshot. Nueve referencias y archivos comprobados por tamaño y SHA-256. Se verificaron nuevamente dump y archivos antes de migrar. pg_dump y pg_restore --list: salida 0. **No se realizó restauración completa**. Se conservaron los respaldos anteriores.

Se ejecutó desde raíz: `.\.venv\Scripts\python.exe backend/manage.py shell -c "exec(open('outputs/rastreo/respaldar_revisiones.py', encoding='utf-8').read())"`. Script operativo local ignorado, adaptado del procedimiento del bloque 2; contraseña solo en entorno privado del subproceso. No repetirlo para consultar la copia existente.

Verificación de solo lectura:

```powershell
$revisionBackup = 'D:\Respaldos_BecaNexo\becanexo_pre_revisiones_20261029T103140Z_bd8aa7ea'
$revisionManifest = Get-Content -LiteralPath (Join-Path $revisionBackup 'manifiesto.json') -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath (Join-Path $revisionBackup 'becanexo_db.backup') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $revisionManifest.dump_sha256) { throw 'Dump inconsistente' }
foreach ($item in $revisionManifest.archivos) {
    $documentPath = Join-Path (Join-Path $revisionBackup 'documentos') $item.archivo
    if ((Get-Item -LiteralPath $documentPath).Length -ne $item.bytes) { throw 'Tamaño inconsistente' }
    if ((Get-FileHash -LiteralPath $documentPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.sha256) { throw 'Documento inconsistente' }
}
& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' --list (Join-Path $revisionBackup 'becanexo_db.backup')
if ($LASTEXITCODE -ne 0) { throw 'Listado fallido' }
```

Las secciones siguientes conservan procedimientos y respaldos anteriores.

El archivo `pg_dump` de becanexo_db **no incluye** HTML/PDF de `RASTREO_STORAGE_ROOT`. Un respaldo utilizable debe conservar base, documentos y un manifiesto que relacione hashes/rutas con el punto de captura. No borrar evidencia ni sobrescribir respaldos anteriores.

## Respaldo utilizado para el bloque 2

Antes de aplicar 0003/0004/0005 se comprobó la copia informada `D:\Respaldos_BecaNexo\becanexo_rastreo_20261027_183559`: seis documentos y listado legible. No podía garantizarse que incluyera todas las escrituras posteriores de PostgreSQL, por lo que se creó una carpeta nueva, sin sobrescribirla:

**D:\Respaldos_BecaNexo\becanexo_pre_bloque2_20261028T000340Z_b52939e9**

Contiene `becanexo_db.backup` (170062 bytes), `documentos/` (seis archivos), `manifiesto.json` y `pg_restore-list.txt`. Captura mediante snapshot PostgreSQL exportado, compartido con pg_dump, metadatos leídos en la misma transacción REPEATABLE READ y bloqueo de exclusión SIAU durante la copia. Se comprobaron huellas/tamaños, pg_dump exit 0 y pg_restore --list exit 0. Al reanudar el 28/10 se revalidaron SHA-256 del dump y seis archivos, y el listado volvió a salir 0. **No se ejecutó una restauración completa**.

Comprobación de solo lectura, reproducible desde la raíz en PowerShell:

```powershell
$respaldoBloque2 = 'D:\Respaldos_BecaNexo\becanexo_pre_bloque2_20261028T000340Z_b52939e9'
$manifiestoBloque2 = Get-Content -LiteralPath (Join-Path $respaldoBloque2 'manifiesto.json') -Raw | ConvertFrom-Json
$dumpBloque2 = Join-Path $respaldoBloque2 'becanexo_db.backup'
if ((Get-FileHash -LiteralPath $dumpBloque2 -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifiestoBloque2.dump_sha256) { throw 'Huella de dump distinta' }
foreach ($documentoBloque2 in $manifiestoBloque2.archivos) {
    $archivoBloque2 = Join-Path (Join-Path $respaldoBloque2 'documentos') $documentoBloque2.archivo
    if ((Get-Item -LiteralPath $archivoBloque2).Length -ne $documentoBloque2.bytes) { throw 'Tamaño distinto' }
    if ((Get-FileHash -LiteralPath $archivoBloque2 -Algorithm SHA256).Hash.ToLowerInvariant() -ne $documentoBloque2.sha256) { throw 'Huella documental distinta' }
}
& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' --list $dumpBloque2
if ($LASTEXITCODE -ne 0) { throw 'Listado fallido' }
```

Esta copia es **previa a las migraciones del bloque 2 y a la ejecución real 2**; no contiene sus nuevas publicaciones/versiones ni los tres HTML posteriores. La integridad actual se verificó separadamente con `rastreo integridad`: nueve documentos, cero problemas, cero eliminados. Una captura conjunta posterior y una restauración completa aislada siguen siendo verificaciones operativas pendientes, no implícitas en el listado del dump. Los apartados siguientes conservan la evidencia y el procedimiento del bloque 1.

## Antes de migrar

1. Ejecutar pruebas, revisar sqlmigrate y migrate --plan. Para este bloque, únicamente rastreo.0001_initial y rastreo.0002_integridad_historial.
2. Crear nombre único en `D:\Respaldos_BecaNexo`, por ejemplo `becanexo_pre_rastreo_<UTC>_<UUID>.dump` en formato custom mediante pg_dump 16, con el usuario de aplicación existente. No usar cuenta administradora ni cambiar permisos. Contraseña desde entorno privado del proceso o archivo pgpass protegido; nunca en argumentos, historial o documentación.
3. Comprobar exit code 0 y tamaño del archivo; ejecutar `pg_restore --list <archivo>`. Ese listado verifica legibilidad del índice, **no prueba restauración completa**. Si cualquiera falla, no migrar desarrollo y conservar el archivo incompleto identificado para diagnóstico.
4. Aplicar solo el plan revisado tras esas comprobaciones. No restaurar sobre desarrollo.

La ejecución realizada y ruta concreta se registran en avance.md; se mantuvo el respaldo previo fuera del repositorio.

Respaldo previo efectivamente creado: `D:\Respaldos_BecaNexo\becanexo_pre_rastreo_20261027T110925Z_031edeb8.dump`, 127902 bytes. pg_dump salió 0 y pg_restore --list salió 0. Es anterior a las seis tablas/documentos del rastreo; no debe confundirse con respaldo posterior del bloque completo.

Comprobación reproducible del archivo existente, sin escribir en ninguna base:

```powershell
Get-Item -LiteralPath 'D:\Respaldos_BecaNexo\becanexo_pre_rastreo_20261027T110925Z_031edeb8.dump' | Select-Object Name,Length
& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' --list 'D:\Respaldos_BecaNexo\becanexo_pre_rastreo_20261027T110925Z_031edeb8.dump'
if ($LASTEXITCODE -ne 0) { throw 'No se pudo listar el respaldo' }
```

Para un nuevo dump manual (no ejecutarlo para simplemente consultar el previo), con nombre único y contraseña solicitada de forma interactiva, nunca como argumento:

```powershell
$rastreoDump = Join-Path 'D:\Respaldos_BecaNexo' ('becanexo_' + [guid]::NewGuid().ToString() + '.dump')
& 'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe' -W --format=custom --host localhost --port 5432 --username becanexo_app --file $rastreoDump becanexo_db
if ($LASTEXITCODE -ne 0) { throw 'Respaldo incompleto: conservar para diagnóstico' }
& 'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe' --list $rastreoDump
if ($LASTEXITCODE -ne 0) { throw 'Listado del respaldo falló' }
```

## Captura conjunta periódica/manual

Por ahora no hay programación automática. Para una copia conjunta: detener nuevos rastreos (desactivar mediante servicio auditado) y comprobar que no hay una ejecución viva; esperar a terminar o recuperar solo tras obtener exclusión. Evitar también cambios administrativos durante la captura. Obtener dump nuevo, copiar toda la raíz documental a una carpeta nueva dentro del respaldo y producir manifiesto SHA-256 de los archivos. Conservar los temporales/huérfanos identificados, sin limpieza automática. Registrar carpeta original, configuración de extractor/normalizador, fecha UTC y alcance de la copia. Los archivos son inmutables, pero los metadatos y accesos requieren un punto consistente; no presentar una copia concurrente incompleta como respaldo cerrado.

Verificar que cada TEC_DOCUMENTO_RASTREO del dump tenga archivo con tamaño/hash correspondientes en la copia. Incluir la versión de código/migraciones y variables **no secretas** necesarias; credenciales se gestionan aparte. Almacenar el respaldo con permisos apropiados al contenido. Su retención y eliminación requieren una política aprobada; este módulo no implementa ninguna.

## Recuperación aislada

Solo en una base y carpeta nuevas dedicadas a recuperación, nunca en becanexo_db ni sobre la raíz real. Restaurar dump con pg_restore, configurar RASTREO_STORAGE_ROOT a la copia aislada y ejecutar `rastreo integridad`; comprobar conteos, claves, FK y triggers. Mantener fuentes desactivadas y bloquear red durante el ejercicio; no lanzar rastreos por accidente. Un ensayo de restauración completo se documenta únicamente cuando se haya ejecutado. En esta etapa el requisito mínimo es comprobar pg_dump y pg_restore --list; no se afirma una restauración completa.

Verificaciones realmente realizadas, que son distintas:

- **Integridad documental real:** seis referencias/archivos, tamaños y huellas correctos, cero problemas; ninguna eliminación.
- **Recuperación de ejecución interrumpida:** pruebas PostgreSQL en test_becanexo_db, con bloqueo de origen/fuente y rechazo de trabajador vivo; no restaura un respaldo.
- **Respaldo/restauración de archivos aislados:** test_document_backup_restore_in_isolated_directories copia evidencia sintética a carpeta temporal de respaldo, simula ausencia del original temporal y recupera en otra carpeta temporal; comprueba bytes/huella/tamaño mediante integridad contra metadatos de test_becanexo_db. No toca D:\Datos_BecaNexo\rastreo y no restaura el dump PostgreSQL.
- **Listado del dump previo:** verificado con pg_restore --list. No se ejecutó restauración completa PostgreSQL, ni se creó una base auxiliar para forzarla, ni se alteraron permisos.

Pendiente operativo opcional: ensayo completo de restauración conjunta en un entorno independiente autorizado y disponible, y captura de un respaldo conjunto posterior al rastreo. No se declara completado por el listado o por el test aislado de archivos.
