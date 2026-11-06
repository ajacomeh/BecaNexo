# Propuestas de integración: bloque de trabajo fuera del catálogo

## Estado operativo y precisión de datos

`rastreo.0010`–`0012` ya están aplicadas en desarrollo y cerradas en los commits `280ca453` y `0b74132`. Las instrucciones inferiores que las llaman pendientes son registro histórico. El esquema `convocatorias.0003`–`0004` se probó en `test_becanexo_db`, se ensayó en una copia restaurada y se aplicó en desarrollo el 06/11/2026.

Una propuesta puede conservar `cierre_original` y añadir `cierre_dia` (ISO `YYYY-MM-DD`) si la evidencia revisada respalda ese día. Al crear el borrador se guarda el día sin inventar hora; un beneficio candidato con `tope` conserva el literal en `tope_original`, sin escribirlo como `monto` ni atribuir moneda. Número y moneda se registran después como valores canónicos revisados, mediante los campos propios del beneficio. La mera presencia del literal no resuelve `PRECISION_TEMPORAL`, `TOPE_FUENTE` ni `TOPE_NO_REPRESENTADO`: la resolución sigue siendo una acción administrativa explícita con evidencia documental aprobada de la versión exacta, procedencia y hash/version canónicos. Los demás pendientes y la salvaguarda de publicación se mantienen. La precisión de apertura por día sigue sin representación canónica.

## Segundo bloque: creación de borrador y procedencia (05/11/2026)

Las rutas nuevas requieren administrador activo y sesión Django; POST exige CSRF y las respuestas de cuenta usan `no-store`. Las migraciones rastreo 0010–0012 están aplicadas en desarrollo; la sección inferior conserva el contrato y resultados históricos del primer bloque.

| Ruta | Uso |
| --- | --- |
| POST `propuestas/:id/crear-borrador/` | Crea borrador vinculado: 201; reintento idéntico 200. Propuesta sustituida, clave reutilizada o contexto obsoleto: 409. Bloqueos/datos inválidos: 400. |
| GET `convocatorias/:id/origen/` | Devuelve aplicación, publicación, versión/observación exacta, pendientes y resoluciones vigentes para el editor. Convocatoria manual: `aplicacion: null`. |
| POST `convocatorias/:id/origen/` | Registra resolución motivada de pendiente con evidencia exacta aprobada y snapshot canónico esperado: 201; reintento 200; obsolescencia 409. Nunca edita la propuesta aplicada. |

`crear-borrador` recibe `clave_accion` UUID, `hash_propuesta`, `observacion_base_id`, lista completa `revisiones`, `motivo_institucion`, `motivo_bases_ausentes` si no hay bases, `confirmados` con **todos** los IDs candidatos, y listas `opciones`, `beneficios`, `requisitos` de elementos elegidos `{id, datos, motivo}`. Cada elemento elegido exige procedencia exacta en la propuesta. `datos` pasa por el serializer vigente del catálogo; no se admiten mapeos que cambien el texto/tipo/ámbito sin guardarlos primero en una sucesora. Un candidato no elegido queda en la propuesta y se enumera como `omitido` en la aplicación. Los requisitos se guardan `validado=false` aunque el cliente envíe otro estado. Los documentos siguen privados.

El servicio vuelve a evaluar revisiones, observación, integridad documental, institución EC, URL oficial pública y duplicados **dentro de la transacción**; un resultado previo de `validar` no reserva permiso. La respuesta incluye `convocatoria_id`, `propuesta_id`, `revision_integracion_id`, revisión y pendientes. La convocatoria nace `activa=false`, `revision=pendiente` y no aparece en `/api/becas/` ni por su ID. La acción `publicar` mantiene controles manuales existentes y, únicamente si hay auditoría de integración, bloquea pendientes materiales o revisiones de origen cambiadas. Día sin hora, tope económico y ámbito no representado permanecen sin conversión automática.

La resolución envía `{clave_accion, pendiente_id, evidencia_id, motivo, version_convocatoria, hash_convocatoria}`. Solo se registra si el pendiente pertenece a la aplicación, la evidencia es de la versión exacta y tiene revisión documental vigente, y los datos actuales acreditan la corrección. Para un candidato se exige además la referencia de procedencia de ese candidato y correspondencia de ámbito, opción y destino. Cambiar la convocatoria invalida una resolución anterior: se permite rectificar con otra fila. Un dato que el modelo todavía no representa no puede resolverse mediante este endpoint. El editor muestra historial y enlaces administrativos de procedencia; la API pública no muestra estos campos.

Procedimiento histórico de rastreo.0010–0012: respaldo conjunto y restauración aislada, revisión del plan/SQL y aplicación autorizada en desarrollo. Ya se completó; no repetirlo por esta ampliación de campos de convocatorias.

Revisión manual del segundo bloque realizada por el usuario con sesión administradora. Para revisar los campos de precisión de este bloque: abrir `/gestion/convocatorias/:id`, comprobar día sin hora y literal de tope en datos sintéticos, y consultar `/becas/:id` únicamente para una oferta de prueba publicada en entorno aislado. Guardar o resolver modifica datos y auditoría; no usar SIAU real como dato de prueba.

Implementación del 05/11/2026. Las migraciones rastreo 0008 y 0009 están **aplicadas en desarrollo según confirmación del usuario**, con respaldo previo y Django check satisfactorio. El usuario confirmó también la revisión manual de crear/continuar propuesta, guardado, historial y validación. No crea convocatorias, no habilita su vínculo y no publica.

Administrador activo, sesiones, CSRF en POST/PATCH y respuestas no-store. Los documentos continúan privados. No se realizan peticiones externas al guardar ni validar.

Prefijo `/api/gestion/rastreo/`:

| Operación | Resultado |
| --- | --- |
| GET `publicaciones/:id/propuesta/` | Historial paginado (`page`, `page_size`, máximo 50), más `contexto` con última observación exitosa, versión y revisiones vigentes. |
| POST `publicaciones/:id/propuesta/` | Primera propuesta: 201; reintento idéntico: 200 con el mismo snapshot. |
| GET `propuestas/:id/` | Snapshot inmutable, origen, autor, datos, procedencia, revisiones y validación guardada. |
| PATCH `propuestas/:id/` | Crea sucesora y devuelve 200 con nuevo ID. El ID de URL es la revisión esperada. Envía el snapshot completo de trabajo, no un delta. |
| POST `propuestas/:id/validar/` con `{}` | Devuelve `guardado`, `actual` y `contexto_cambio`; no modifica el snapshot. |

No existen endpoints crear-borrador ni resoluciones. Errores: 400 petición inválida/referencia ajena; 403 permisos/CSRF; 404 identificador inexistente; 405 método no admitido; 409 clave reutilizada con contenido diferente o cabecera sustituida.

## Entrada y semántica

```json
{
  "clave_accion": "11111111-1111-4111-8111-111111111111",
  "version_id": 10,
  "observacion_base_id": 20,
  "revisiones": [],
  "datos": {},
  "procedencia": []
}
```

IDs ilustrativos. Información incompleta es válida; `{datos:{}}` no equivale a una petición inválida. No se aceptan autor, fechas de autoría, aprobación, estados del catálogo ni campos desconocidos. Esquema de contrato 1; autor y fecha proceden del servidor/BD.

`datos` acepta título (250), descripción (15000), institución existente nullable, URL oficial HTTP/S sin credenciales (2048), apertura/cierre literales (500) y listas `opciones`/`beneficios`/`requisitos` (50/50/100). Los elementos son **candidatos**, no objetos del catálogo: identificador estable, texto, nivel/modalidad/destinos mencionados, concepto, cantidades literales, moneda, tope, tipo, condiciones y ámbito pendiente/común/opción/destino. No se convierten menciones en códigos de catálogo ni se interpretan cantidades como números confirmados. Una referencia a opción debe existir en la misma propuesta. Identificadores de elementos no se repiten.

`procedencia`: lista de campo (o `opciones.ID`, `beneficios.ID`, `requisitos.ID`), `evidencia_id` de REL_VERSION_DOCUMENTO —no ID del archivo—, localizador, original opcional y motivo obligatorio. La evidencia debe corresponder a la versión. Los documentos y revisiones de otra versión se rechazan.

Las opciones pueden incluir `paises`, lista explícita de códigos existentes en CAT_PAIS (por ejemplo `EC`), independiente de `destinos`, el texto literal que se conserva. Un requisito/beneficio con `destino` debe referenciar una opción de la misma propuesta y un código incluido en sus `paises`. No se interpreta una lista literal para generar países. Ámbito `comun` con opción/destino o ámbito `opcion` con destino son peticiones incoherentes (400). Ámbito `destino` aún sin seleccionar opción/país es trabajo incompleto admisible y genera `AMBITO_INCOMPLETO`. Ámbito desconocido conserva `pendiente`; nunca se convierte en común.

Al cambiar ámbito u opción en pantalla se mantienen las referencias anteriores para que el administrador decida retirarlas o corregirlas. Cambiar versión de origen conserva texto/localizadores/motivos de procedencia, pero deja la evidencia sin seleccionar: debe asignarse explícitamente una relación de la nueva versión. Las respuestas de validación de campos se muestran como texto y no borran el formulario.

Cada pendiente contiene `id` estable por código/campo, `codigo`, `campo`, `motivo`, `condicion_resolucion`. Se separan `bloqueos` de creación futura y `pendientes_publicacion`; `creacion_habilitada` siempre es false. `puede_crear` es una evaluación preliminar de bloqueos, nunca una autorización operativa ni certificación de mapeo final.

Se comprueban contexto, aprobaciones vigentes, bases, integridad local, datos mínimos y procedencia. Candidatos continúan pendientes de interpretación y mapeo final; rellenar texto no los acredita. Las fechas literales y topes se conservan. Una fecha observada en fuente no deja de estar pendiente por vaciar el formulario. No se amplían ni relajan serializers del catálogo.

Reintentos mantienen clave; una edición intencional obtiene otra. Un contexto desactualizado puede conservarse como snapshot de trabajo bloqueado. La acción explícita de actualizar contexto conserva datos; si cambia versión, exige volver a referenciar evidencia y no traslada aprobaciones. El historial anterior permanece consultable. El formulario avisa que validar usa el último snapshot guardado.

## Comprobación manual y ejecución aislada

La aplicación en desarrollo ya fue realizada por el usuario. Los comandos siguientes se conservan como referencia operativa; no constituyen una tarea pendiente ni se ejecutaron durante este cierre documental.

Desde la raíz, consulta de estado, plan y SQL (solo lectura):

```powershell
.\.venv\Scripts\python.exe backend/manage.py showmigrations rastreo
.\.venv\Scripts\python.exe backend/manage.py migrate rastreo 0009_integridad_propuestas --plan
.\.venv\Scripts\python.exe backend/manage.py sqlmigrate rastreo 0008
.\.venv\Scripts\python.exe backend/manage.py sqlmigrate rastreo 0009
```

Comando de aplicación conservado para otros entornos donde falten estas migraciones: `.\.venv\Scripts\python.exe backend/manage.py migrate rastreo 0009_integridad_propuestas`. No es necesario repetirlo para cerrar este bloque en desarrollo. En otros entornos, revisar plan y respaldo antes de aplicarlo; no reordenar ni duplicar migraciones.

Abrir `/gestion/rastreo`, consultar una publicación y usar Crear/Continuar propuesta. Guardar un título, una fecha literal y un beneficio con tope; comprobar pendientes, historial, validación y recarga. Dos pestañas sobre la misma revisión permiten comprobar el conflicto y actualización explícita. Estas acciones sí crean snapshots: para pruebas automatizadas usar exclusivamente el entorno aislado.

Para revisar ámbitos: añadir opción, seleccionar países candidatos del catálogo, dejar un beneficio en «Pendiente de interpretar» y asignar un requisito a un destino de esa opción. Guardar/recargar debe conservar ambos estados. Cambiar a «Toda la convocatoria» con referencias todavía seleccionadas explica la incoherencia sin borrarlas; retirar explícitamente lo que no corresponda. Consultar historial y comprobar que las revisiones anteriores permanecen intactas.

Recorrido reproducible: Node 24, `node frontend/e2e/proposals-real.mjs --reset-test-db` desde la raíz. Reutiliza el servidor auxiliar `integration_server.py`, que rechaza cualquier BD distinta de test_becanexo_db y usa almacenamiento temporal. **Reinicia datos de la BD de pruebas**, por lo que no debe ejecutarse simultáneamente con una suite. Las credenciales sintéticas se generan en memoria; no se imprimen ni versionan. Las capturas quedan en `frontend/test-results`, ignorado por Git. El ejecutor cierra únicamente sus propios servidores.

El ejecutor de propuestas también limpia la BD aislada al finalizar mediante `integration_server.py cleanup --test-db-only`, después de cerrar Django. Ese subcomando vuelve a verificar el nombre configurado y `current_database()` antes de hacer flush. Así no quedan escenarios sintéticos que contaminen otras suites; no modifica desarrollo. La ejecución final y su limpieza terminaron con código 0.

Resultados actuales (05/11/2026): 67 pruebas de rastreo aprobadas, incluidas 14 de propuestas; 23 frontend de propuesta/bandeja con simulación aprobadas; lint, build, Django check y coherencia de migraciones correctos. Recorrido real aislado y capturas a 1440/390/320 px revisados. Detalle de incidencias, repetición puntual y límites en `avance.md`; los conteos no suman reejecuciones.
