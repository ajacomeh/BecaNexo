# Contrato propuesto de integración entre rastreo y catálogo

## Estado vigente de precisión de datos

Las migraciones `rastreo.0010`–`0012` se aplicaron en desarrollo y el segundo bloque quedó cerrado en Git. El bloque actual añade `cierre_dia` separado del instante `cierre` y campos de tope distintos del importe fijo; sus migraciones `convocatorias.0003`–`0004` se aplicaron en desarrollo el 06/11/2026. Los extractos literales y los snapshots revisados siguen separados de valores canónicos. Día de cierre y tope solo entran al borrador con procedencia y nunca levantan por sí solos pendientes editoriales. La publicación conserva revisión exacta, resolución motivada y las demás restricciones. Apertura sin hora, opciones con identidad ambigua y actualización de convocatorias vinculadas permanecen fuera de este bloque.

## Estado del segundo bloque, 05/11/2026

Se implementaron la creación de **convocatoria nueva en borrador** desde propuesta vigente, el vínculo protegido, auditorías humanas separadas, selección confirmada de hijos, procedencia administrativa en el editor y la salvaguarda de publicación para convocatorias integradas. El servicio vuelve a validar el contexto y persiste borrador, hijos, vínculo y auditorías en una transacción. La publicación automática, actualización de canónicas existentes, ampliaciones de fechas/topes/opciones y nuevos rastreos permanecen fuera de alcance. Las migraciones 0010–0012 fueron probadas en `test_becanexo_db` y después aplicadas en desarrollo con autorización. Los controles anteriores de publicación manual ajena a la integración conservan su comportamiento.

La aplicación registra el resultado de la propuesta, todos los IDs confirmados, elementos omitidos y motivos. La resolución posterior de un pendiente material crea una fila de auditoría con aplicación, evidencia exacta y hash/versión canónicos; una edición invalida esa decisión hasta una rectificación. Un cierre con precisión de día, un tope o una condición que el modelo no representa no se resuelve con casilla ni se convierte a un dato ficticio. El historial y la versión pública previa permanecen conservados. Para contrato operativo de rutas y entrada véase `api-propuestas-rastreo.md`; para pruebas actuales `avance.md`. Las secciones siguientes documentan el diseño original y el primer bloque como registro histórico, por lo que sus frases de «futuro» se refieren al momento en que se redactaron.

## Actualización: primer bloque aprobado e implementado (05/11/2026)

El diseño que sigue se conserva como referencia de la integración completa. Se aprobaron e implementaron **solo propuestas de trabajo y validación**, mediante `rastreo.Propuesta`, `PropuestaRevision`, `propuestas.py`, `api_propuestas.py` y `CrawlingProposal.jsx`. Migraciones 0008/0009 probadas por el ejecutor únicamente en test_becanexo_db y posteriormente aplicadas en desarrollo según confirmación del usuario, con respaldo previo, Django check correcto y revisión manual satisfactoria del flujo de propuestas. Esta confirmación no es una nueva ejecución de pruebas automatizadas. Contrato efectivo de endpoints/entrada en `api-propuestas-rastreo.md` y suplemento `Modelo/Propuestas_integracion_rastreo.md`.

- Propuesta incompleta no equivale a petición inválida: faltantes de negocio pueden guardarse; campos desconocidos, tipos y referencias incoherentes se rechazan.
- Guardar propuesta no crea un borrador de convocatoria. El vínculo sigue prohibido por CHECK y trigger; no se añadieron aplicaciones, resoluciones ni modificaciones de publicación.
- Cada pendiente tiene identificador estable, código, campo/elemento afectado, motivo y condición de resolución. Validación guardada es inmutable; reevaluar devuelve ambos resultados y señala cambios.
- Los elementos académicos/económicos/documentales son candidatos literales pendientes, no opciones o requisitos confirmados. El mapeo final mediante todos los serializers del catálogo y su creación corresponden al siguiente bloque. No se presenta `puede_crear` como certificación de ese mapeo; `creacion_habilitada` siempre es false.
- Cambios respecto al ejemplo de diseño: procedencia es una lista cerrada de referencias, publicación tiene FK explícita para unicidad verificable, se conserva también hash de petición para reintentos y no se amplía aún AUD_REVISION_RASTREO. El PATCH guarda un snapshot completo como sucesor, no actualiza columnas de la revisión anterior.

Las condiciones para futura creación de borradores ya están aprobadas por la instrucción de implementación; las secciones históricas que las describen como pendientes no requieren volver a solicitarlas. Representación temporal/económica, integración canónica y actualizaciones posteriores permanecen fuera del alcance ejecutado.

Precisión de cierre del bloque: destinos literales no se convierten automáticamente en países. El formulario permite seleccionar códigos CAT_PAIS por opción candidata; beneficios/requisitos solo pueden referenciar esa opción y uno de sus países. Ámbito desconocido o todavía incompleto se guarda como pendiente; ámbito contradictorio o referencias ajenas son errores de petición. La interfaz conserva valores ante conflictos, muestra errores del servidor y requiere selección documental nueva cuando cambia la versión, preservando los textos de procedencia. Las pruebas/resultados actuales se registran en `avance.md`, sin sumar ejecuciones repetidas.

Registro histórico del diseño inicial: **propuesta para aprobación, entonces no implementada**. Revisión: 5 de noviembre de 2026. Base examinada: `9145be7305f7463b742339cc4685a844cb6d16a0`. Las secciones siguientes conservan el diseño completo; el alcance efectivamente implementado es exclusivamente el indicado en la actualización anterior.

## 1. Estado real y piezas reutilizables

| Evidencia en el repositorio | Implementado | Límite actual |
| --- | --- | --- |
| `backend/rastreo/models.py`: `Publicacion`, `Version`, `VersionDocumento`, `Observacion` | Identidad por fuente/URL, versiones y documentos exactos, historial de consultas | `Publicacion.convocatoria` existe, pero el CHECK `rast_publicacion_sin_vinculo` exige NULL. No hay integración habilitada. |
| `backend/rastreo/migrations/0004_integridad_versiones.py`: `rastreo_publicacion_guard` | Protege identidad y permite actualizar última detección | También impide vincular. Quitar solo el CHECK o añadir un endpoint no bastaría. |
| `backend/rastreo/observaciones.py`: `observe`, `differences` | Persistencia bajo bloqueo, reutilización de versiones; diferencias entre extracciones | El diff no compara ni combina campos de la convocatoria canónica. |
| `backend/rastreo/revisiones.py`: `registrar`, `vigentes`; migración `0007_integridad_revision_editorial.py` | Revisiones independientes, rectificaciones inmutables, evidencia exacta, actor real, idempotencia y conflictos | Una revisión de oferente identifica tipo y referencia documental, no una FK a `Institucion`. Aprobar convenios continúa bloqueado. |
| `backend/rastreo/api.py`, `urls.py`; `frontend/src/pages/Crawling.jsx`, `components/CrawlingReviews.jsx` | Consulta administrativa, selección de versiones, revisión y descarga protegida | No existe formulario de integración ni propuesta persistida. |
| `backend/convocatorias/models.py` y `serializers.py` | Instituciones EC; convocatoria, opciones, beneficios, requisitos y sus validaciones | Hay restricciones de representación temporal, económica y académica descritas abajo. |
| `backend/convocatorias/api.py`: `Convocatorias`, `Hijos`, `Accion`; `services.py`: `audit`, `touch`, `publicar`, `publicas` | Gestión manual, auditoría, revisión previa a publicar y visibilidad pública | No comprueban procedencia de rastreo ni pendientes de una importación. |
| `frontend/src/pages/OfferEditor.jsx`, `App.jsx` | Editor y rutas `/gestion/convocatorias/nueva`, `/gestion/convocatorias/:id` | Deben recibir un borrador ya creado por un servicio explícito; no simular una serie de guardados desde el navegador. |

`docs/propuesta-persistencia-rastreo.md` propuso `TRA_PROPUESTA_CAMBIO` y una ampliación de auditoría; **no son capacidades presentes por aparecer en ese documento**. Se reutilizan esos conceptos, sin crear un segundo sistema de propuestas. El modelo v0.6 es histórico y debe interpretarse con los suplementos existentes, especialmente `docs/Modelo/Revision_administrativa_rastreo.md`. No se modifica ninguno en esta tarea.

El cierre anterior está en `docs/validacion-entrega-integracion.md`. Sus resultados no son pruebas nuevas de este contrato. No se consultó la BD en esta tarea: no se afirma que existan aprobaciones editoriales reales aplicables hoy.

### Borrador, revisión y publicación no son lo mismo

El serializer manual admite una convocatoria con institución y título, sin descripción, cierre ni opciones. `Convocatoria.revision` empieza en `pendiente`; `activa` tiene actualmente valor predeterminado verdadero. Un borrador sigue oculto porque `publicas()` exige activa, revisión validada e institución EC. La integración debe fijar explícitamente revisión pendiente y conservar esa semántica, sin presentar `activa` como aprobación.

`publicar()` exige título, descripción, enlace oficial, alguna opción activa, requisitos activos validados y ausencia de superposiciones rechazadas por sus reglas. Actualmente no exige destinos, fecha de cierre, beneficios o requisitos cuando las respectivas colecciones están vacías. Una oferta cerrada puede seguir siendo consultable; cerrada no significa rechazada.

Las condiciones más estrictas de **publicación automática** en `docs/decisiones-recomendacion-rastreo.md` no sustituyen este flujo manual. Esta propuesta no habilita automatismos ni amplía silenciosamente esas condiciones a todas las convocatorias.

## 2. Alcance mínimo recomendado y recorrido

Primera integración: **crear una nueva convocatoria en borrador desde una publicación no vinculada**, con selección y confirmación humanas. No enlazar todavía una convocatoria existente, cambiar vínculos, actualizar convocatorias desde la fuente ni publicar desde la bandeja de rastreo.

1. En `/gestion/rastreo/publicaciones/:id`, abrir la versión seleccionada y sus revisiones. Ofrecer «Preparar borrador» solo con explicación de los requisitos pendientes; no ocultar la razón de un bloqueo. La versión inicial continúa siendo la de la última observación exitosa, no el número más alto.
2. Mostrar fuente, URL original/normalizada, número e ID de versión diferenciados, observación base, documentos y SHA, revisiones vigentes de cada dimensión. Una versión histórica puede consultarse, pero la primera integración se propone únicamente desde la última observada con éxito.
3. Abrir una propuesta administrativa separada del catálogo. Presentar, por campo, extracción original, evidencia y valor propuesto. Precargar texto fiel y candidatos inequívocos; dejar sin seleccionar los códigos de catálogo, asociaciones y ámbitos no demostrados. La propuesta puede guardarse incompleta sin crear una convocatoria.
4. Seleccionar una institución EC existente y justificar que corresponde al oferente revisado. Si falta, usar la gestión existente de entidades y volver; no crear instituciones automáticamente ni interpretar la procedencia SIAU como identidad del oferente.
5. Completar opciones, beneficios y requisitos únicamente mediante decisiones explícitas respaldadas. Reutilizar controles/validadores existentes. Cada cambio semántico respecto de lo extraído requiere motivo y referencia exacta; limpiar espacios sin cambiar significado puede registrarse como transformación técnica.
6. Validar y presentar dos listas separadas: «Impide crear el borrador» y «Pendiente para completar/publicar». Mostrar el resumen final; «Crear borrador vinculado» requiere confirmación y clave de acción estable durante reintentos.
7. Crear borrador, hijos seleccionados, vínculo y auditoría en **una transacción**. Abrir `/gestion/convocatorias/:id`. Ningún requisito se marca `validado` por haber aprobado extracción/documentación. El administrador continúa su revisión con el flujo habitual.
8. Mostrar «Procedencia del rastreo» en el editor, con enlace a publicación, versión exacta y propuesta aplicada. Mantener ese origen aunque lleguen nuevas observaciones. Los documentos privados solo se consultan mediante los endpoints administrativos existentes.

### Puertas propuestas para las transiciones

Estas puertas son recomendaciones que requieren aprobación antes de implementarse; no se presentan como reglas ya vigentes.

| Transición | Condiciones recomendadas |
| --- | --- |
| Guardar propuesta de trabajo | Administrador activo, versión existente y coherencia estructural. Puede tener revisiones pendientes, datos vacíos y bloqueos identificados; no produce datos de catálogo. |
| Crear borrador vinculado | Última observación exitosa confirmada; extracción y oferente con revisiones vigentes aprobadas de esa versión; identidad de institución EC confirmada; título y enlace oficial comprobados; documentación utilizada aprobada por relación exacta; ausencia de contradicciones materiales y duplicado sin resolver. |
| Documentación necesaria | Si la versión identifica bases oficiales, exigir su revisión exacta y disponibilidad íntegra antes de integrar; no eludirlo omitiéndolas del formulario. Un anexo no utilizado puede quedar pendiente si se justifica por qué no condiciona los datos. Si no existen bases identificadas, documentar esa ausencia y limitar el borrador a información respaldada; no fabricar una revisión documental. |
| Crear borrador incompleto | Se permite omitir opciones, descripción u otros campos opcionales que el contrato admite, con pendientes explícitos. Un hijo inválido nunca se inserta parcialmente: permanece en la propuesta. Datos contradictorios que cambian la elegibilidad o identidad impiden la creación hasta aclararlos. |
| Publicar después | Acción manual existente y sus validaciones. Recomendada una salvaguarda **solo para borradores procedentes de integración**: impedir publicar mientras haya información material conocida omitida por falta de representación (cierre por día, tope, ámbito ambiguo). No extenderla a ofertas manuales ajenas. Requiere aprobación expresa. |

La salvaguarda no declara automáticamente resuelto un pendiente porque se rellenó un campo. Su resolución exige evidencia, motivo y una nueva constancia administrativa de integración; nunca reescribir la propuesta aplicada. Cuando falta capacidad de modelo, como un cierre solo por día, el pendiente no se puede resolver inventando un instante: espera la ampliación independiente aprobada. Hasta entonces esos borradores no podrán completar publicación. Los pendientes puramente informativos no bloquean por defecto.

## 3. Mapeo y límites de representación

Los destinos de esta tabla son campos actuales, salvo indicación expresa. Las transformaciones son candidatas revisables, no reglas de extracción automática.

| Dato de origen | Evidencia | Destino | Transformación permitida | Validación | Ausencia o contradicción |
| --- | --- | --- | --- | --- | --- |
| Identidad y URL de ficha | `Publicacion`, observación y manifiesto de `Version` | Vínculo existente `Publicacion.convocatoria`; procedencia de propuesta | Conservar URL original y normalizada según política de fuente | Fuente+URL sigue siendo identidad; no título ni SHA como identidad entre fuentes | Sin identidad válida, bloquear. Redirect no fusiona publicaciones. |
| Enlace oficial | Enlace y contexto de ficha/bases de versión exacta | `Convocatoria.url_oficial` | Elegir el enlace verificado; no usar ruta de almacenamiento | HTTP/S sin credenciales, destino público permitido y pertinencia oficial revisada | No inferir que todo enlace de SIAU es plataforma de postulación; bloquear el mínimo recomendado si no puede verificarse. |
| Oferente | Revisión `oferente` y su `VersionDocumento`, texto/localizador | `Convocatoria.institucion` | Selección explícita de `Institucion` existente | País código EC y misma entidad respaldada; registrar snapshot de identidad | Nombre similar no basta. Convenio no representable o difusor de oferta extranjera: bloquear. |
| Título y descripción | Texto original y sección HTML/PDF | `titulo`, `descripcion` | Texto seguro, limpieza de espacios; corrección relevante con motivo | Longitudes actuales, título no vacío, sin HTML ejecutable | Descripción ausente puede quedar vacía en borrador; divergencia material requiere revisión. |
| Apertura/cierre | Literal, localizador, precisión y zona explícita | `apertura`, `cierre` DateTime; `cierre_original` | Solo instante inequívoco; conservar literal del cierre | Orden cronológico y zona/offset demostrados | Día sin hora: DateTime NULL, literal y estructura en propuesta, pendiente material. Nunca 00:00/23:59 inventados. |
| Fecha de publicación | Fecha declarada de la fuente | `fecha_publicacion` Date | Día inequívoco publicado | No usar fecha de descarga/registro como sustituto | Desconocida permanece NULL; fecha ambigua conserva literal en propuesta. |
| Programa/nivel/modalidad | Estudios efectivamente ofertados y bases revisadas | `OpcionEstudio.programa`, `nivel`, `modalidad` | Selección humana de códigos existentes | No confundir formación previa con oferta; respetar UNIQUE convocatoria+nivel+modalidad | «Maestría tecnológica» no equivale a tercer nivel tecnológico. Dos programas distintos con igual nivel/modalidad no se fusionan para satisfacer UNIQUE; requieren decisión/modelado posterior. |
| Destinos | Países explícitos para una opción concreta | `OpcionEstudio.paises` por `REL_OPCION_ESTUDIO_PAIS` | Resolver códigos del catálogo; confirmación por opción | Sin inferir destino desde oferente, residencia o modalidad virtual | Lista vacía admitida actualmente; declarar desconocido. No generar combinaciones cartesianas de menciones. |
| Beneficio/concepto | Literal, condiciones y ámbito | `Beneficio.concepto`, `detalle`, `opcion_estudio` nullable | Transcribir concepto y condiciones, asignar ámbito confirmado | Concepto obligatorio y opción perteneciente a convocatoria | Ámbito desconocido no se transforma en común. Mantener candidato pendiente. |
| Porcentaje | Concepto financiado y porcentaje explícito | `porcentaje` | Decimal sin cambiar base financiada | 0–100 y restricciones vigentes | Sin porcentaje: NULL, no cero. 100 % matrícula no significa 100 % de todos los gastos. |
| Importe/moneda/periodicidad | Literal con unidad y condiciones | `monto`, `moneda`, `periodicidad` | Importe fijo demostrado, moneda explícita y periodicidad actual | Monto no negativo, moneda requerida al informar monto; no conversiones | `$` aislado no decide ISO. No introducir monto sin moneda ni reinterpretar un máximo como asignación fija. |
| Tope económico | Límite explícito y concepto afectado | **Sin campo actual equivalente**; literal en propuesta/detalle | Preservar texto, candidato estructurado separado | No mapear a `monto` ni ocultar límite de un porcentaje | Recomendada futura ampliación `tope_monto` con moneda/ámbito aprobados; bloquea publicación integrada si su omisión desfigura el beneficio. |
| Elegibilidad común | Condición explícita, no puntuación ni obligación posterior | `Requisito`: opción/destino NULL, `texto_original`, tipo y JSON | Transcripción y estructuración humanas con reglas existentes | `RequisitoSerializer` y `reglas.validar`; `validado=False` inicialmente | Mostrar «Toda la convocatoria». Dudas permanecen en propuesta; no adjudicar significado nuevo. |
| Elegibilidad por opción/destino | Sección exacta que determina alcance | `opcion_estudio`, `destino` | Referencia temporal de opción resuelta a FK al crear | Misma convocatoria y destino incluido en la opción | Sin alcance fiable no insertar como requisito común. Conservar reglas de misma formación, equivalencias y fechas de referencia actuales. |
| Documentos exigidos | Bases revisadas y requisito concreto | DOCUMENTO/ACREDITACION, campos complementarios y JSON actuales | Conservar nombre, condiciones, enlace y descripción en sus propiedades distintas | Contratos actuales; no perder valores complementarios ni confundirlos con aprobación del postulante | Verificación externa siempre pendiente de entidad; no pedir certificados al postulante. |
| Bases oficiales | Relación exacta `bases_pdf` y revisión documental | `Convocatoria.url_bases`; referencia privada de procedencia | URL oficial comprobada, nunca endpoint privado como URL pública | Existencia del enlace no demuestra revisión; documento asociado a versión exacta | Varias bases no caben en un único URL: conservar todas en procedencia y seleccionar principal justificadamente; no perder condiciones de anexos. |

La URL segura del serializer valida formato y ausencia de credenciales; no prueba por sí sola oficialidad. El servicio de integración no hará peticiones de red. Su validación de enlaces y la revisión humana no deben convertirse en un nuevo descargador ni permitir enlaces internos/privados para el catálogo.

Precisiones del contrato documental actual (`backend/convocatorias/reglas.py`): DOCUMENTO utiliza `valor_estructurado.documento`, `condiciones` y `url_documento`; ACREDITACION utiliza `certificados_admitidos`, `vigencia` y `url_documento`. Los campos de modelo `documento_exigido`, `detalle_acreditacion` y `referencia_bases` son distintos y no se colapsan ni borran durante el mapeo. La `fecha_referencia` del requisito es una fecha publicada para interpretar la condición, no la fecha en que se registra la propuesta. El enlace al documento exigido tampoco sustituye a `Convocatoria.url_bases`.

### Evidencia local SIAU utilizada para el diseño

Se consultaron `outputs/rastreo/20261027T043208793284Z/informe.json` y el reprocesamiento `outputs/rastreo/reprocesamiento-20261027T104723600572Z/informe.txt`/`informe.json`, junto a `docs/rastreo-fuentes-iniciales.md`. Son evidencia histórica local; el reprocesamiento declara **sin red**, no una descarga nueva. No se asignan esos archivos retrospectivamente a versiones persistidas.

- **Jóvenes del Nuevo Ecuador 2026:** USD 828.97 de manutención por una sola vez; Ecuador y menciones de estudios técnico/tecnológico/grado. El HTML no identifica nominalmente al oferente en el campo correspondiente. Debe identificarse desde evidencia revisada, no por el nombre del portal. Cierre literal 28 de junio de 2026: día, no instante.
- **Ecuador Productivo:** maestrías, especializaciones y maestrías tecnológicas conservadas como expresiones; no opciones confirmadas. Matrícula/aranceles hasta 100 % con tope literal $3000; no importe fijo ni ISO deducido. Cierre 25 de octubre de 2026 sin hora demostrada. No convertir la mención institucional de institutos tecnológicos en nivel ofertado.
- Las notas de `backend/convocatorias/siau_bases.py` son anotaciones manuales parciales sujetas a URL/SHA, no extracción automática de todo el PDF ni aprobación editorial. La existencia de bytes almacenados tampoco constituye aprobación.
- Ambos cierres son anteriores a la fecha de este análisis. No proponerlos como oportunidades vigentes. Un borrador puede conservar una oportunidad cerrada; su eventual presentación pública debe reflejar esa vigencia y esperar representación temporal fiel.

## 4. Trazabilidad, revisiones y cambios concurrentes

Cada propuesta conserva versión, manifiesto y documentos exactos, observación base, revisiones utilizadas, autor/fecha y valores originales separados de valores propuestos. Por campo o elemento de una lista se registra: identificador estable local, valor extraído, valor propuesto, relación documental/localizador, transformación y motivo de corrección. No sobrescribir `Version.datos_extraidos` ni añadir documentos a una versión cerrada.

Las revisiones deben seguir vigentes al aplicar. La aprobación de extracción avala la transcripción de esa versión; la documental concierne a una relación concreta; la de oferente sustenta admisibilidad, pero no acredita documentos del postulante ni publica una convocatoria. El mapeo a una institución y la confirmación de importación son decisiones separadas, registradas con administrador real.

**A→B→A:** la consulta mantiene la selección por última observación exitosa. Si vuelve A, se reutiliza su versión exacta y pueden seguir existiendo revisiones vigentes de A; esto no hereda aprobaciones de B. La propuesta registra además la observación base. Recomiendo rechazar su aplicación con 409 si esa observación cambió durante la edición, incluso cuando los bytes coinciden: el administrador actualiza contexto y confirma una nueva revisión de la propuesta, sin repetir innecesariamente la aprobación del mismo documento. Si solo hay un fallo posterior sin versión, se conserva la última exitosa y se muestra la incidencia; un 404 no cancela la oferta.

Un cambio de revisión mientras se edita invalida la confirmación anterior aunque el contenido no cambie. Se comparan IDs de revisiones vigentes, no solo etiquetas «aprobada». Una rectificación posterior a crear el borrador deja visible una advertencia de procedencia y requiere nueva evaluación antes de publicar; no borra el borrador ni modifica automáticamente una convocatoria que ya se hubiera publicado.

### Duplicados y transacciones

- Fuente+URL conserva su identidad actual. Entre fuentes no se fusiona por título, similitud o hash documental. La clave de deduplicación del catálogo tiene otro contrato; no reemplaza a la identidad de rastreo.
- Publicación ya vinculada: mostrar su convocatoria y negar una segunda creación, aunque se envíe otra clave de acción. En este primer alcance tampoco se desvincula ni se cambia el destino.
- Coincidencia exacta de la clave de catálogo: devolver conflicto, sin sobrescribir ni vincular automáticamente. Posibles duplicados por título/institución/URL se muestran antes de confirmar; una coincidencia no concluyente requiere justificación de que es distinta. Si se confirma que ya existe, detener creación y dejar la vinculación explícita para un bloque posterior.
- Doble clic/reintento: UUID de acción, actor y huella canónica de entrada. Misma acción/mismo contenido devuelve la misma convocatoria; mismo UUID con otro contenido devuelve 409. Consultar el resultado idempotente antes de rechazar por vínculo ya creado por esa misma acción.
- Propuesta editada por dos administradores: revisiones inmutables de propuesta, CAS contra ID de cabecera esperado, un único sucesor. El perdedor recibe 409 y conserva el texto local; no reemplazarlo con el servidor sin confirmación.
- Orden de bloqueos propuesto, a verificar con pruebas de concurrencia: actor → exclusión de clave de acción → institución → publicación → versión → cabecera de propuesta → convocatoria si procede. Compatible con observación (publicación antes de ejecución) y revisión (actor antes de versión); no invertir órdenes ni mantener transacciones durante red o archivos grandes.
- Bajo esos bloqueos se vuelven a comprobar permisos, última observación, revisiones, institución, integridad documental, vínculo, payload y duplicados. Serializar con escritores existentes; no fiarse de lo visto al abrir el formulario.
- Crear convocatoria/hijos/relaciones, vínculo, auditoría de negocio y constancia de integración en una sola transacción. Fallo de cualquier parte revierte todo. Recuperar `IntegrityError` con savepoint para traducir colisiones esperadas, sin continuar una transacción rota. El rollback no deja un borrador sin procedencia ni una auditoría de aplicación inexistente.

### Actualización futura, fuera del primer alcance

Una observación nueva no cambia la convocatoria. Comparar tres estados: propuesta aplicada, nueva evidencia y estado canónico actual completo con relaciones. Usar `differences` como ayuda de extracción, no como política de combinación. Preparar otra propuesta con versión canónica y hash de snapshot; marcar campos corregidos manualmente y conflictos por campo. Aplicar solamente decisiones explícitas bajo bloqueo y volver a comprobar contador **y** snapshot. No sobrescribir correcciones ni copiar automáticamente requisitos de un PDF nuevo.

La actualización de una oferta publicada debe distinguir edición que requiere nueva revisión de datos ya públicos. El comportamiento actual de `touch()` devuelve a pendiente; no prometer conservar una versión pública anterior sin diseñar su representación. Ese punto necesita diseño específico en el bloque futuro, no una supuesta capacidad de versionado editorial que hoy no existe.

Recomendación para ese bloque futuro: guardar la propuesta sin tocar la canónica y conservar así su estado público durante la revisión. Si se aplica una modificación sustantiva mediante el comportamiento actual, comunicar que devuelve la convocatoria a pendiente hasta publicar de nuevo. Mantener además una edición pública anterior mientras se modifica otra exigiría versionado editorial adicional y aprobación de ese alcance; no se incluye aquí.

## 5. Contrato técnico propuesto

Todos los elementos de esta sección que amplían el código son **propuestos**. No reservar numeraciones de migración antes de implementar y comprobar el árbol real.

### Persistencia mínima

1. **Reutilizar `Publicacion.convocatoria`.** Migración posterior elimina solo la prohibición de vínculo y adapta el trigger: identidad inmutable; NULL→convocatoria permitido únicamente con constancia de integración de la misma publicación/transacción; vínculo existente no se reemplaza ni borra. Mantener protección de borrado, fechas e historial. No rellenar publicaciones históricas.
2. **`TRA_PROPUESTA_CAMBIO`**, nombre recuperado del diseño anterior. Cada fila es una revisión inmutable de una propuesta editable en pantalla. Campos propuestos: `id bigint`, `version_id` FK obligatoria, `observacion_base_id` FK obligatoria, `sustituye_id` FK propia nullable, `actor_id` FK obligatoria, `creada_en timestamptz`, `clave_accion uuid UNIQUE`, `contrato_version integer > 0`, `datos jsonb`, `procedencia jsonb`, `pendientes jsonb`, `hash_propuesta char(64)`. Payload con esquema cerrado versionado y valores tipados; nunca código ejecutable. FK protegidas. Sello de transacción e inmutabilidad en BD siguiendo el patrón existente.
3. **`REL_PROPUESTA_REVISION`**, relación nueva mínima: `id`, `propuesta_id`, `revision_id`, UNIQUE del par, FK protegidas, filas inmutables insertadas con la propuesta. Evita referencias huérfanas a aprobaciones guardadas solo como números en JSON. Las relaciones documentales señaladas en `procedencia` deben pertenecer a la versión; validación de servicio y trigger de integridad, no confianza en JSON recibido.
4. En la cadena, sucesor único por `sustituye_id`; misma publicación para todos sus miembros. Una raíz por publicación, comprobada bajo bloqueo y restricción/trigger en BD (la publicación se obtiene de versión). Cambiar la versión de evidencia crea sucesor, no cambia una fila histórica. Propuestas aplicadas no se editan; una integración aplicada se identifica por auditoría. Abandono y reapertura de una propuesta no crean otra raíz para eludir concurrencia.
5. **Ampliar `AUD_REVISION_RASTREO`**, no duplicar auditoría: FK nullable `propuesta_id`, `convocatoria_id`; dimensión propuesta `integracion`, decisiones `aplicada` y `resuelta` para constancias posteriores de pendientes. La aplicación exige propuesta+versión+convocatoria coherentes, actor real y motivo; UNIQUE parcial de aplicación por propuesta. La resolución exige referencia a aplicación original, motivo y evidencia, sin sustituirla ni quitar la unicidad de creación. Separar su cadena de las rectificaciones de extracción/documental/oferente. Adaptar CHECK/triggers sin cambiar filas antiguas; la evidencia detallada se referencia desde propuesta y resolución, no se reutiliza incorrectamente el campo documental obligatorio de otras dimensiones.
6. **`AUD_EVENTO` existente** registra creación de convocatoria con su actor y snapshot. No sirve para propuesta sin convocatoria porque exige un objeto de negocio. Extender `audit` de manera compatible para añadir procedencia de integración (IDs de publicación/versión/propuesta/revisión), manteniendo sus consumidores actuales. La acción humana asistida no se registra como publicación automática.

La edición visual de propuesta produce otra fila; el endpoint PATCH debe explicar que devuelve el nuevo ID. Esto concreta la inmutabilidad del diseño anterior sin introducir una tabla mutable paralela. Los campos de base canónica y sus relaciones para actualizaciones se incorporarán en el bloque futuro; no hace falta simularlos con ceros en la primera creación.

Integridad adicional del contrato propuesto:

- `observacion_base_id` debe ser una observación exitosa de la misma publicación y apuntar a `version_id`. Cada revisión de `REL_PROPUESTA_REVISION` debe pertenecer a esa versión. Al guardar trabajo puede estar pendiente; al aplicar se exige su vigencia y aprobación según la puerta correspondiente.
- Una sucesora conserva publicación, referencia a antecesora y autoría propia; no puede ser su propia antecesora ni formar ciclos. El hash incluye datos, procedencia, pendientes derivados, observación y revisiones ordenadas, además de la versión de contrato. No basta con comparar título o solo el payload del catálogo.
- La inserción de relaciones de propuesta queda limitada a su transacción de creación mediante sello y trigger; después no se añaden aprobaciones a un snapshot antiguo. Conservar FK protegidas e inmutabilidad, siguiendo los suplementos actuales (Django PROTECT y restricciones SQL correspondientes), sin afirmar que todas las FK existentes usan SQL ON DELETE RESTRICT.
- Para resolver pendientes, añadir a `AUD_REVISION_RASTREO` una FK propia nullable propuesta `aplicacion_id`: obligatoria en dimensión integración/decisión resuelta y referida a la aplicación original de esa misma propuesta y convocatoria. Guardar en `detalle` el identificador estable del pendiente, evidencia exacta y snapshot/hash de los campos canónicos que fundamentan la resolución. La resolución no modifica datos de negocio ni sustituye la aplicación. Un cambio posterior de esos campos obliga a reevaluarla; no sirve como autorización permanente.
- Ampliar CHECK/triggers y consultas editoriales para que la nueva dimensión no aparezca como aprobación de extracción/documentación/oferente. `vigentes()` actualmente devuelve decisiones de todas las dimensiones de una versión: sus consumidores deberán filtrarlas explícitamente al incorporarse integración. Mantener intactas las cadenas históricas y su unicidad.
- El guard de vínculo debe comprobar también inserciones: una nueva publicación nace sin convocatoria. Para NULL→FK, una comprobación diferida al commit verificará la constancia de integración y su sello de transacción; el guard inmediato conserva identidad y monotonicidad de última detección. Así se permite ordenar los INSERT/UPDATE atómicos sin abrir un bypass por insertar directamente una publicación vinculada.

No se añaden campos a opciones, beneficios o fechas en este primer bloque. Sus limitaciones se conservan explícitas. Las futuras ampliaciones temporales/económicas requieren contrato y migración independientes. Todas las migraciones propuestas son aditivas o ampliaciones controladas de restricciones, sin transformar evidencia ni valores antiguos; revisar SQL y respaldar antes de cualquier aplicación futura autorizada.

### Servicios, API y seguridad

Servicios nuevos sugeridos en `backend/rastreo/integracion.py`: `guardar_propuesta`, `validar_propuesta`, `crear_borrador`. Son nombres propuestos, no símbolos existentes. Reutilizar serializers de convocatorias y reglas; extraer únicamente las operaciones de persistencia compartidas indispensables (incluida asignación de países), sin llamar endpoints HTTP internos ni duplicar validación. La vista entrega `request.user`; se rechazan actor, publicación destino arbitraria, estados de aprobación y campos desconocidos del cliente.

Rutas propuestas bajo `/api/gestion/rastreo/`:

| Método/ruta nueva | Contrato |
| --- | --- |
| GET/POST `publicaciones/:id/propuesta/` | Consultar cabecera o crear raíz; GET no tiene efectos; POST 201, reintento idéntico 200. |
| PATCH `propuestas/:id/` | Enviar revisión esperada, clave de acción y cambios; guardar sucesor inmutable, devolver 200 con su nuevo ID. |
| POST `propuestas/:id/validar/` | Validación sin persistencia; 200 con `puede_crear`, bloqueos y pendientes. No reserva aprobación ni garantiza que el estado no cambie después. |
| POST `propuestas/:id/crear-borrador/` | Confirmación de snapshot/observación/revisiones; 201 y referencia a borrador; reintento 200 al mismo resultado. |
| GET `propuestas/:id/` | Snapshot, procedencia, historial de sucesores y resultado de aplicación, para consulta desde el editor. |
| POST `propuestas/:id/resoluciones/` | Solo bloque de creación vinculado, tras aprobación de la salvaguarda: registrar resolución motivada de un pendiente contra aplicación y snapshot canónico esperados; 201, reintento idéntico 200, contexto obsoleto 409. No cambia campos de la convocatoria ni elimina pendientes históricos. |

Mantener sesiones, CSRF en escrituras, administrador activo y respuestas `no-store`. No asumir que `is_staff` concede rol de negocio. Anónimo, postulante e inactivo: 403 según el contrato DRF de sesiones actual; CSRF fallido también 403, con código/mensaje distinguible sin información sensible. 400 para formato/campos/validación, 404 para recurso ausente o relaciones incoherentes no revelables, 409 para concurrencia/idempotencia/duplicados/vínculo, 503 para evidencia local temporalmente no disponible. Un fallo de integridad documental se explica y bloquea; no se descarga de nuevo como efecto lateral. No capturar indiscriminadamente todo error como conflicto.

Los errores llevan `codigo`, `detail` y, cuando corresponda, errores por campo y referencia de estado actual. No incluyen rutas físicas, credenciales, cabeceras o contenido privado fuera de permisos. En frontend conservar formulario y clave ante fallo de red; un 409 ofrece comparar/recargar contexto antes de reenviar, sin sobrescribir texto. Carga deshabilita duplicados; éxito solo cuando el servidor confirma la transacción.

Documentos: seguir usando `/api/gestion/rastreo/documentos/:id/descarga/`, protegido por administrador activo, como adjunto y con integridad comprobada. Nunca copiar HTML a recursos públicos ni publicar enlaces locales. Un enlace oficial público a bases es distinto de una descarga privada de evidencia. No cambiar la API pública ni incluir metadata editorial privada en `detalle(..., publico=True)`.

La descarga existente responde 409 cuando el archivo no está disponible o es inconsistente (`Descargar.get`); el 503 descrito arriba es una opción **nueva** para indisponibilidad temporal en integración, no una descripción ni un cambio de ese endpoint. La futura implementación debe mantener mensajes coherentes sin reescribir su contrato como efecto colateral.

## 6. Ejemplo sintético de contrato

IDs y contenido siguientes son ilustrativos; **no corresponden a registros reales**. Las listas detalladas de opciones/beneficios/requisitos usarían el esquema de los serializers existentes, con claves locales para resolver relaciones en la transacción.

```json
{
  "clave_accion": "11111111-1111-4111-8111-111111111111",
  "version_id": 901,
  "observacion_base_id": 1201,
  "revisiones": [1301, 1302, 1303],
  "datos": {
    "institucion": 701,
    "titulo": "EJEMPLO SINTÉTICO · Estudios de posgrado",
    "descripcion": "Descripción transcrita de evidencia sintética revisada.",
    "url_oficial": "https://example.org/convocatoria",
    "apertura": null,
    "cierre": null,
    "cierre_original": "30 de noviembre de 2026",
    "opciones": [],
    "beneficios": [],
    "requisitos": []
  },
  "procedencia": {
    "titulo": {"evidencia_id": 1001, "localizador": "encabezado", "transformacion": "transcripcion"},
    "institucion": {"evidencia_id": 1002, "localizador": "bases, apartado oferente", "motivo": "Correspondencia de identidad comprobada"}
  }
}
```

Servidor deriva pendientes y huella; no confía en un `puede_crear` ni en aprobaciones enviados por cliente. El cierre del ejemplo permite conservar un borrador incompleto según la política recomendada, pero deja pendiente material temporal. Una respuesta de validación podría ser:

```json
{"puede_crear":true,"bloqueos":[],"pendientes":[{"codigo":"CIERRE_SOLO_DIA","bloquea_publicacion":true},{"codigo":"SIN_OPCIONES","bloquea_publicacion":true}]}
```

Tras aplicación válida: `201 {"convocatoria_id":801,"revision":"pendiente","publica":false,"propuesta_id":1401,"revision_integracion_id":1501}`. Una revisión reemplazada entretanto: `409 {"codigo":"REVISION_CAMBIADA","detail":"Cambió una revisión utilizada. Conserva tus cambios y revisa el contexto actualizado."}`. No hay creación parcial ni autoaprobación en ninguno de estos casos.

## 7. Criterios de aceptación que deberá probar la implementación

**Casos definidos, no ejecutados en esta tarea.** Usar PostgreSQL `test_becanexo_db`, suite secuencial y archivos temporales; pruebas de concurrencia con conexiones independientes dentro del caso. Navegador con datos sintéticos aislados o API simulada claramente identificada; nunca escribir aprobaciones reales de SIAU para demostrar funcionamiento.

| Caso | Resultado exigido |
| --- | --- |
| Creación completa y trazable | Un borrador, relaciones correctas y dos auditorías coherentes; usuario/fecha del servidor, requisito sin auto-validar, invisible públicamente por lista e ID. |
| Propuesta incompleta | Se guarda fuera del catálogo; validación distingue campos inválidos, bloqueos y pendientes. Hijos incompletos no se insertan. |
| Revisiones/evidencia insuficientes | Extracción u oferente pendientes/rechazados, bases necesarias no revisadas, archivo ausente o hash incorrecto impiden creación; no se produce descarga. |
| Identidad y convenios | Rechazo de institución distinta a la revisada, país no EC y convenio no representable; sin institución ficticia. |
| Fechas/beneficios | Cierre por día no se convierte en instante; una fecha vencida no pasa a vigente. Tope no se vuelve monto; moneda desconocida no se completa por suposición. |
| Opciones y requisitos | No crear combinaciones por menciones, no degradar maestría tecnológica, no convertir puntuación en elegibilidad; ámbitos y relaciones corresponden a la misma convocatoria/opción/destino. |
| Reintentos y duplicados | Misma clave devuelve mismo resultado; clave con otro payload 409; dos claves concurrentes no crean dos canónicas para la publicación. Duplicado entre fuentes se informa sin fusionar. |
| Concurrencia de propuesta | Dos PATCH de la misma cabecera dejan un único sucesor; el cliente perdedor conserva el texto. |
| Observación/revisión nueva, A→B→A | Contexto obsoleto produce 409; selección respeta última observación exitosa; ninguna revisión de B acredita A ni viceversa. |
| Transacción fallida | Inyectar fallo después de crear hijos/auditoría/vínculo: rollback íntegro; reintento recuperable sin filas huérfanas. |
| Permisos/CSRF | Anónimo, postulante e inactivo rechazados en consulta y escritura; CSRF ausente/incorrecto rechazado con cliente real; actor no puede suplantarse. |
| Inmutabilidad histórica | Revisiones, versiones, documentos y propuestas anteriores sin cambios; acceso ORM directo no elude integridad. |
| Publicación | Crear o aprobar evidencia jamás publica; guardia de pendientes materiales no se elude llamando directamente al endpoint existente. Ofertas manuales ajenas mantienen reglas actuales. |
| Documentos privados | Sin rutas físicas ni HTML ejecutable; documento de otra versión no puede presentarse como revisado; API pública no expone propuesta ni auditoría. |
| Frontend | Foco/teclado, móvil y escritorio; evidencia legible, errores por campo, carga, reintento y conflictos sin pérdida de valores; diferenciar guardado de propuesta y creación de borrador. |
| Actualizaciones futuras | Definir más adelante prueba de tres vías: nueva fuente no cambia canónica ni correcciones manuales; edición concurrente impide aplicar snapshot obsoleto. No declarar ese flujo implementado en el bloque inicial. |

## 8. Implementación por bloques y decisiones

### Decisiones de negocio que requieren aprobación

| Decisión nueva | Recomendación concreta y efecto |
| --- | --- |
| Momento de crear borrador | Permitir propuesta incompleta antes de aprobaciones; exigir extracción/oferente y documentación necesaria aprobadas al crear. Evita mezclar trabajo preliminar con catálogo. |
| Mínimo y pendientes de integración | Exigir institución identificada, título y enlace oficial; permitir borradores incompletos trazables. Aprobar guardia limitada de publicación y resolución motivada de pendientes materiales. SIAU puede producir borradores, pero cierres/topes aún no representables impiden completar su publicación. |
| Bases inexistentes/anexos | Ausencia real documentada no crea revisión ficticia; bases identificadas son obligatorias para la integración; anexo no pertinente puede excluirse con motivo. |
| Alcance de vinculación | Primera versión solo crea canónica nueva desde última observación; duplicado confirmado se detiene. Enlazar una canónica existente y actualizarla quedan para bloque posterior. |
| Suplemento de modelo | Aprobar propuesta inmutable editable por sucesores, relación a revisiones y ampliación de auditoría/vínculo protegido descritas aquí. No altera evidencia histórica. |
| Representaciones posteriores | Conservar día sin inventar hora y máximo separado de monto; aprobar contrato de precisión/vigencia y tope/moneda antes de ampliarlos. Para programas distintos con igual nivel/modalidad, diseñar identidad de opción antes de importarlos, sin fusionarlos. No bloquea implementar propuestas, sí los casos que dependen de esa representación. |
| Actualización de una oferta ya pública, etapa posterior | Recomiendo conservar la canónica sin cambios durante la preparación y revisión de la propuesta; al aplicar cambios sustantivos, conservar la vuelta a pendiente del flujo actual. Si se desea publicar una edición anterior simultáneamente, aprobar antes un alcance separado de versionado editorial. |

No se solicita reaprobación de Ecuador como ámbito, verificación externa, privacidad documental, conservación de correcciones, separación de afinidad y requisitos, ausencia de publicación automática ni prohibición de inventar convenios: son decisiones existentes. Una descarga correcta sigue sin equivaler a aprobación.

Decisiones técnicas rutinarias resolubles al implementar: serialización determinista/huellas, nombres exactos de errores, reutilización de validadores, CAS y claves idempotentes, controles de accesibilidad, transacciones/savepoints, índices, límites de payload y pruebas de bloqueo. No requieren modificar reglas de negocio ni consultar cada detalle. La comprobación de observación base más estricta puede implementarse como protección de contexto sin convertirla en nueva aprobación documental.

### Orden recomendado

1. **Primer bloque implementable tras aprobación: propuesta persistida y validación, todavía sin creación canónica.** Incorporar `TRA_PROPUESTA_CAMBIO`, relación de revisiones e integridad; servicios y API de consulta/guardado/validación; formulario desde la bandeja con procedencia y errores. Mantener todavía prohibido el vínculo. Terminado cuando pruebas sintéticas demuestren inmutabilidad, CAS, permisos/CSRF, revisiones exactas, A→B→A, mapeos sin inferencias y cero cambios de catálogo; migración revisada y probada en BD de pruebas, no aplicada a desarrollo sin autorización.
2. **Creación atómica del borrador y consulta de origen.** Depende de puertas aprobadas: habilitar vínculo protegido, ampliar auditoría, persistir hijos usando reglas actuales y añadir guardia de publicación/resolución de pendientes. Terminado cuando doble envío, fallos y concurrencia no dejan inconsistencias, borradores permanecen ocultos y el editor puede continuar revisión manual con procedencia íntegra. Este bloque completa el primer flujo para datos representables; no implica que todo SIAU pueda publicarse.
3. **Representación fiel de casos pendientes.** Contratos y migraciones independientes para precisión temporal, topes y opciones si se aprueban. Resolver pendientes con evidencia y auditoría; no convertir retrospectivamente datos desconocidos.
4. **Vínculo a canónicas existentes y actualizaciones.** Diseñar comparación de tres vías, conflictos, publicación durante revisión de cambios y conservación de correcciones. No habilitar combinación por similitud ni herencia de aprobaciones.

No forman parte de estos bloques IA, afinidad, nuevas fuentes, planificación diaria o publicación automática. Esta entrega termina en el diseño: no inicia ninguno de los bloques.

## 9. Verificación documental de esta entrega

Se revisaron rutas y símbolos del repositorio, restricciones de vínculo, serializers, servicios de publicación/auditoría, revisiones y evidencia local. Se conservaron la guía de arquitectura sin seguimiento y todos los archivos pendientes del cierre. Único archivo añadido por esta tarea: `docs/contrato-integracion-rastreo-catalogo.md`.

No se ejecutaron suites, Django check, migraciones ni consultas de escritura. Los casos de la sección 7 son compromisos de verificación futura, no resultados. La disponibilidad y vigencia real de aprobaciones/documentos deberán comprobarse en cada operación futura; este análisis local no las certifica.

En la reanudación se contrastaron específicamente `Publicacion` y `rastreo_publicacion_guard`, `publicas`/`publicar`/`touch`, `RevisionEntrada`/`registrar`/`vigentes`, la selección por última observación en `rastreo/api.py`, la descarga protegida y los contratos DOCUMENTO/ACREDITACION. Se completaron integridad de referencias, resolución de pendientes, inserción inicial sin vínculo y alcance de actualización futura; se corrigió la numeración. Ninguna de esas ampliaciones propuestas se implementó.
