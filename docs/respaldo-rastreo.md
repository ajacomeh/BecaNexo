# Respaldo conjunto de PostgreSQL y documentos

El archivo `pg_dump` de becanexo_db **no incluye** HTML/PDF de `RASTREO_STORAGE_ROOT`. Un respaldo utilizable debe conservar base, documentos y un manifiesto que relacione hashes/rutas con el punto de captura. No borrar evidencia ni sobrescribir respaldos anteriores.

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
