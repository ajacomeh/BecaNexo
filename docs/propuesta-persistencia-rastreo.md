# Propuesta de persistencia del rastreo

Actualización 29/10/2026: se implementó el subconjunto editorial autorizado del bloque 3, reutilizando AUD_REVISION_RASTREO para extracción, documento exacto y oferente. Véase [suplemento efectivo](Modelo/Revision_administrativa_rastreo.md). No incluye TRA_PROPUESTA_CAMBIO, vinculación, publicación ni resolución de incidencias. La propuesta original que sigue conserva esos elementos como futuros, no implementados.

Estado actualizado al 28/10/2026: **bloques 1 y 2 aprobados e implementados**; resto del diseño pendiente. El JSON v0.6 se conserva histórico. Las secciones siguientes conservan el diseño original para trazabilidad y no deben interpretarse como que las once tablas ya existen. Se leyeron AGENTS, Diccionario, decisiones aprobadas, contrato SIAU e informe real `outputs/rastreo/20261027T043208793284Z/informe.json` y su HTML.

Implementadas CFG_FUENTE, TRA_EJECUCION_RASTREO, TEC_DOCUMENTO_RASTREO, TRA_ACCESO_RASTREO, TRA_INCIDENCIA_RASTREO y AUD_REVISION_RASTREO (solo configuración/incidencias). Migraciones 0001_initial y 0002_integridad_historial aplicadas en pruebas y desarrollo. Se aprobó archivo privado separado, conservación sin borrado automático y ejecución manual con administrador real; aprobación automática permanece bloqueada. Campos, diferencias y restricciones efectivas en [suplemento implementado](Modelo/Persistencia_rastreo_bloque1.md). No se modificaron entidades del catálogo.

El bloque 2 añade TRA_PUBLICACION_FUENTE, TRA_VERSION_PUBLICACION, REL_VERSION_DOCUMENTO y TRA_OBSERVACION_RASTREO, con relaciones opcionales en accesos/incidencias. Migraciones 0003/0004/0005 aplicadas en pruebas y desarrollo; ejecución real 2 finalizada con dos publicaciones/versiones/observaciones y cuatro relaciones documentales. El [suplemento del bloque 2](Modelo/Persistencia_rastreo_bloque2.md) especifica ajustes técnicos y límites reales. La ejecución 1 permanece sin asociaciones retrospectivas.

Continúan **sin implementar** TRA_PROPUESTA_CAMBIO, las dimensiones de revisión editorial y el vínculo/creación de convocatorias. Tampoco publicación automática, planificación diaria, convenios ni integración de fechas/topes. Las expresiones «propuesto», «pendiente» y el plan de bloques del documento original se refieren al diseño de entonces; el estado operativo actual se resume aquí y en avance.md.

## Correcciones comprobadas

El informe de las 04:32 devolvía grado/tecnológico mediante coincidencias de subcadenas en Posgrado/tecnológicos. El código posterior ya tenía límites de palabra, pero perdía el término compuesto maestrías tecnológicas. Ahora se conservan expresiones compuestas y contexto, separando oferta mencionada, formación previa, mención incidental y contexto por revisar. No se normalizan a catálogos. La clasificación léxica es conservadora, no un intérprete universal: una condición sobre título previo para cursar un posgrado no acredita que ese posgrado sea la formación previa exigida. Las expresiones dudosas permanecen pendientes con texto original.

Reprocesar el HTML ya descargado de Productivo produce como oferta mencionada: maestrías, especializaciones, maestrías tecnológicas; institutos superiores tecnológicos queda incidental. Se mantienen el informe y archivos originales; el reprocesamiento no es una descarga nueva.

Los timestamps originales 04:32:08.803124 y 04:32:09.622227 se generaban en fetch **antes** de entrar a once y esperar. Robots participaba en el mismo Downloader/last, sin excepción. Por ello no prueban un intervalo de red de 0,819 segundos. El limitador anterior se ubicaba antes de DNS: tampoco instrumentaba los inicios de request tras latencias DNS variables. Se sitúa ahora después de DNS/preparación, inmediatamente antes de invocar request, y se registran inicio_peticion_utc e inicio_peticion_monotonic. consulta_utc en el historial sigue siendo admisión del intento; en el resultado de descarga usa la marca de petición. La marca es la invocación de la operación HTTP (incluye conexión/TLS), no una medición de paquetes en el cable. Reloj monotónico solo comparable dentro del proceso; UTC sirve para correlación, no para controlar la pausa. No se afirma un fallo histórico de pausa no medido. El limitador es local a una instancia secuencial, no distribuido.

## Convenciones y garantías del diseño

- Cada tabla tiene `id bigint GENERATED ... PRIMARY KEY NOT NULL`, salvo indicación contraria. En las listas de campos, **todos son NOT NULL excepto los marcados `?`**, que admiten SQL NULL. Tipos PostgreSQL; timestamps timestamptz en UTC. SHA-256: char(64), CHECK hexadecimal minúsculo. JSONB con esquema versionado y validado en servidor, nunca código ejecutable. Texto no vacío donde representa identidad/motivo.
- Todas las FK usan **ON DELETE RESTRICT / Django PROTECT**; no hay cascadas destructivas, SET NULL ni eliminación automática. Índices en FK y fechas de consulta. Tablas históricas inmutables no admiten UPDATE/DELETE desde aplicación; futura migración incluirá protección de inmutabilidad en BD (trigger) para evitar bypass con QuerySet.update. Corregir evidencia/revisión crea otra fila. No se cambian hoy permisos PostgreSQL.
- Relaciones de pertenencia entre tablas se validarán mediante FK compuestas sobre pares UNIQUE y, donde el ORM no las exprese, constraints/triggers explícitos de migración. Validación de servicio adicional, no sustituto de integridad. Rol administrador activo se comprueba bajo transacción en el momento de actuar; cambiar el rol después no invalida autoría histórica.
- Documentos y versiones no equivalen a aprobación. No fusionar fuentes por títulos, similitud ni hash documental. Varias publicaciones pueden vincularse tras revisión a una convocatoria, sin perder identidades independientes.

## 1. CFG_FUENTE — configuración de acceso

Reutiliza el nombre y finalidad del ER. No existe aún como modelo Django del rastreo.

| Campos | Tipo / contenido |
| --- | --- |
| nombre, tipo, adaptador | varchar(160), varchar(12) publico/privado, varchar(100) identificador de código permitido |
| url_base | text UNIQUE; validada, sin credenciales |
| frecuencia_min, espera_seg, timeout_seg | integer > 0, >= 0, > 0 respectivamente |
| activa | boolean default false: habilita acceso, no publicación |
| aprobada_publicacion_automatica | boolean default false, autorización editorial distinta |
| politica_acceso, politica_version | jsonb (lista cerrada de destinos/límites), varchar(60) |
| creada_en | timestamptz |

Cambios v0.6: aprobación explícita y política versionada. La política no contiene scripts ni secretos y nunca permite anular validación IP/TLS. Cambios de configuración/aprobación requieren AUD_REVISION_RASTREO con administrador y antes/después; flag aprobado derivable de su última decisión, actualizado en la misma transacción. Desactivar fuente no borra evidencia ni revoca automáticamente publicaciones. Índice en activa. Borrado protegido por todas sus relaciones.

## 2. TRA_EJECUCION_RASTREO — cada invocación

FK fuente_id → CFG_FUENTE. Campos: clave_idempotencia uuid UNIQUE; origen varchar(16) manual/programada; solicitado_por_id bigint? → MAE_USUARIO; inicio timestamptz; fin timestamptz?; estado varchar(20) en_curso/finalizada/parcial/fallida/omitida; configuracion_snapshot jsonb; version_extractor varchar(80); version_normalizador varchar(60); latido_en timestamptz?; publicaciones_observadas integer default 0; versiones_nuevas integer default 0; observaciones_sin_cambios integer default 0; error_resumen text?.

CHECK contadores >= 0, fin >= inicio, fin nulo solo en_curso; manual exige administrador real, programada exige solicitado_por nulo. UNIQUE parcial (fuente_id) WHERE estado=en_curso. Una invocación concurrente distinta se registra como omitida con motivo; un reintento de la misma clave recupera su fila. Configuración snapshot permite explicar una ejecución aun si fuente cambia. Una ejecución sin cambios sigue registrada y contiene observaciones.

Diferencia v0.6: se sustituyen nuevas/actualizadas (que significaban convocatorias) por contadores de observación; no falsear publicaciones. Se añaden identidad de invocación, origen, versión/configuración y estado omitida. No elimina auditoría existente; no inventa actor para cron. Finalizadas son inmutables; mientras en curso solo se actualizan cierre, latido y contadores bajo servicio controlado.

## 3. TRA_PUBLICACION_FUENTE — identidad detectada

Campos: fuente_id bigint → CFG_FUENTE; convocatoria_id bigint? → MAE_CONVOCATORIA; url_original text (primera observada); url_normalizada varchar(2048); normalizacion_version varchar(60); primera_deteccion timestamptz; ultima_deteccion timestamptz.

UNIQUE (fuente_id, url_normalizada); CHECK ultima >= primera. URL mayor a 2048 genera incidencia y no se trunca. Normalizar únicamente esquema/host a minúsculas, puerto HTTPS predeterminado y fragmento; preservar ruta, barra final, codificación y parámetros con significado. Rechazar userinfo; queries sensibles no se admiten. Cambiar política no reescribe identidades antiguas: plan de reconciliación revisado. Redirect no fusiona automáticamente una URL con otra; conservar ambas en acceso y resolver vínculo explícitamente.

Diferencia v0.6: convocatoria pasa a opcional; ejecucion_id, hash_contenido y texto_extraido salen de identidad hacia observación/versión. Fuente sigue obligatoria. Únicamente última detección y vinculación revisada pueden cambiar. Vínculo con convocatoria requiere revisión con administrador, fila bloqueada y auditoría antes/después; versiones no cambian. Sin vínculo, sigue siendo candidata, no borrador ficticio. No se copian requisitos a tablas de negocio al detectarla.

## 4. TEC_DOCUMENTO_RASTREO — bytes inmutables

Campos: sha256 char(64) UNIQUE; tamano_bytes bigint >= 0; mime varchar(100); clave_almacenamiento varchar(180) UNIQUE; creado_en timestamptz. Clave derivada de hash, relativa a raíz configurada fuera del código; nunca un path recibido de la fuente. MIME verificado, admitidos HTML/PDF/texto según función; original preservado, no ejecutable.

Tabla nueva respecto v0.6. Deduplicación física por bytes no fusiona publicaciones. Si hash existente, verificar tamaño y bytes antes de reutilizar; diferencia es incidencia de integridad, no reemplazo. URL/tiempos de cada obtención pertenecen a TRA_ACCESO_RASTREO, no al documento, pues los mismos bytes pueden llegar desde varias fuentes. Evidencia completa se referencia desde versión y acceso; no almacenar PDF binario en JSON.

## 5. TRA_VERSION_PUBLICACION — interpretación inmutable

Campos: publicacion_id bigint → TRA_PUBLICACION_FUENTE; numero integer > 0; creada_en timestamptz; version_extractor varchar(80); version_normalizador varchar(60); version_contrato integer > 0; hash_manifiesto char(64); hash_contenido_relevante char(64); datos_extraidos jsonb; texto_extraido text?; advertencias jsonb; estado_extraccion varchar(20) completa/parcial/fallida.

UNIQUE (publicacion_id, numero) y UNIQUE (publicacion_id, hash_manifiesto, version_extractor, version_normalizador, version_contrato); UNIQUE(id, publicacion_id) para pertenencia. Número asignado bajo bloqueo de publicación. Manifest canónico incluye URL/rol/SHA de todos los documentos y enlaces de bases ausentes con su estado; no tiempos de consulta. Hash relevante incluye campos completos de título, descripción, requisitos, beneficios, estudios, fechas, enlaces y advertencias semánticas; excluye menú/pie/scripts y timestamps. Algoritmo de serialización determinista versionado. Texto original se preserva; no quitar negaciones ni acentos para deduplicar.

Tabla nueva, absorbe hash/texto del ER anterior pero separa byte-hash y contenido relevante. HTML distinto con contenido relevante igual produce versión nueva (y puede indicarse cambio de presentación); no nuevo significado por suposición. PDF diferente siempre cambia manifiesto, aun si no puede extraerse texto. Misma evidencia reprocesada con extractor nuevo es versión distinta. Nueva versión **no hereda aprobaciones**. No mutar sus datos por corrección humana; la corrección vive en propuesta/revisión. Un fallo sin contenido no fabrica una versión vacía: queda acceso/incidencia.

## 6. REL_VERSION_DOCUMENTO — conjunto exacto de evidencia

Campos: version_id bigint → TRA_VERSION_PUBLICACION; documento_id bigint → TEC_DOCUMENTO_RASTREO; rol varchar(20) ficha_html/bases_pdf/anexo; url_original text; url_normalizada varchar(2048); localizador text? (enlace/sección de referencia).

UNIQUE(version_id, rol, url_normalizada); varias bases pueden compartir el mismo documento. UNIQUE(id, version_id) para referenciar evidencia revisada. Inmutable, nuevo en v0.6. El manifiesto incluye exactamente estas relaciones; transacción difiere comprobación hasta tener versión y relaciones completas. No anexar después un PDF a una versión ya finalizada: generar nueva versión. Enlaces fallidos se conservan en datos_extraidos y acceso, no documento ficticio. No hay colección «PDF actual» mutable que sustituya al revisado.

## 7. TRA_OBSERVACION_RASTREO — resultado por publicación y ejecución

Campos: ejecucion_id bigint → TRA_EJECUCION_RASTREO; publicacion_id bigint → TRA_PUBLICACION_FUENTE; version_id bigint? → TRA_VERSION_PUBLICACION; observada_en timestamptz; resultado varchar(24) nueva/sin_cambios/cambio_bytes/cambio_relevante/fallo; detalle text?. UNIQUE(ejecucion_id, publicacion_id).

Nueva en ER. Inmutable. Verificar fuente de ejecución = fuente de publicación y versión pertenece a publicación, mediante restricciones de pertenencia. Fallo implica version_id nulo; resultados de éxito exigen versión. Una publicación sin cambios apunta a versión existente, dejando constancia de consulta; no deducir ausencia solo porque no apareció en un listado. Para A→B→A se reutiliza la versión A y se registra otra observación; el orden temporal está en las observaciones, no en el número de versión reutilizado. Índice (publicacion_id, observada_en).

## 8. TRA_ACCESO_RASTREO — intento real por recurso

Campos: ejecucion_id bigint → TRA_EJECUCION_RASTREO; publicacion_id bigint? → TRA_PUBLICACION_FUENTE; documento_id bigint? → TEC_DOCUMENTO_RASTREO; secuencia integer > 0; rol varchar(20) robots/indice/ficha/bases; url_original text; url_normalizada varchar(2048); url_final text?; admitido_en timestamptz; inicio_peticion_en timestamptz?; fin timestamptz; espera_ms bigint >= 0; duracion_ms bigint? >= 0; http_status smallint?; resultado varchar(20) descargado/reutilizado/bloqueado/error; error_codigo varchar(60)?; etag text?; last_modified text?.

UNIQUE(ejecucion_id, secuencia); CHECK http 100–599 si existe; fin >= admitido y comienzo >= admitido. Es una fila por intento/salto, incluidos robots y reintentos; bloqueo antes de red permite inicio/http nulos. No persistir cookies, Authorization ni headers arbitrarios. Reutilizado (futuro 304) exige documento previo verificable de esa URL; 304 sin evidencia local íntegra es incidencia, no éxito. Resultado descargado exige documento, error no fabrica uno. Fuente coherente si hay publicación. Nueva tabla, inmutable; evita perder intentos al deduplicar documentos/versiones. Milisegundos de duración/espera medidos con reloj monotónico, no resta de UTC.

## 9. TRA_INCIDENCIA_RASTREO — problemas sin objetos ficticios

Campos: fuente_id bigint → CFG_FUENTE; ejecucion_id bigint? → TRA_EJECUCION_RASTREO; publicacion_id bigint? → TRA_PUBLICACION_FUENTE; acceso_id bigint? → TRA_ACCESO_RASTREO; version_id bigint? → TRA_VERSION_PUBLICACION; codigo varchar(60); gravedad varchar(12) aviso/error; detalle text; detectada_en timestamptz; clave_evento uuid UNIQUE.

Nueva respecto ER; sin actor ni convocatoria obligatoria. Coherencia de fuente/ejecución/publicación/versión/acceso por restricciones; una incidencia general de fuente puede no tener ninguna FK contextual. No XOR: puede apuntar a acceso y versión a la vez si coherentes. Inmutable; resolución es una revisión posterior, no borrado. 404, timeout, PDF cambiado, robots denegado y conflicto son códigos, no cancelaciones de ofertas. Clave idempotente por evento, no por mensaje: fallos en ejecuciones distintas conservan ocurrencias.

## 10. TRA_PROPUESTA_CAMBIO — integración candidata

Campos: version_id bigint → TRA_VERSION_PUBLICACION; convocatoria_id bigint? → MAE_CONVOCATORIA; creada_en timestamptz; base_version_convocatoria integer?; base_snapshot jsonb?; base_hash char(64)?; propuesta jsonb; hash_propuesta char(64); contrato_version integer > 0.

UNIQUE(version_id, hash_propuesta), hash calculado también sobre base y convocatoria; propuesta inmutable. Convocatoria nula exige base_version/base_snapshot/base_hash nulos (creación); vinculada exige los tres y versión > 0 (edición). Debe corresponder al vínculo revisado de publicación; una creación no se ejecuta si otra transacción ya la vinculó. Base snapshot contiene campos/relaciones afectados, no datos personales. Nueva en ER: impide editar directamente la oferta publicada. Propuesta incluye decisiones por campo con referencia a evidencia y correcciones humanas; ajustes generan otra propuesta, nunca modifican evidencia.

## 11. AUD_REVISION_RASTREO — decisiones humanas inmutables

Campos: actor_id bigint → MAE_USUARIO; creada_en timestamptz; fuente_id bigint? → CFG_FUENTE; version_id bigint? → TRA_VERSION_PUBLICACION; incidencia_id bigint? → TRA_INCIDENCIA_RASTREO; evidencia_id bigint? → REL_VERSION_DOCUMENTO; propuesta_id bigint? → TRA_PROPUESTA_CAMBIO; convocatoria_id bigint? → MAE_CONVOCATORIA; dimension varchar(24) configuracion/extraccion/oferente/documental/vinculacion/publicacion/incidencia; decision varchar(24) pendiente/aprobada/rechazada/resuelta/aplicada; motivo text; detalle jsonb; clave_accion uuid UNIQUE; sustituye_id bigint? → esta tabla.

CHECK exactamente uno de fuente/version/incidencia como objeto principal; configuración requiere fuente, incidencia requiere incidencia, otras dimensiones requieren versión. Documental exige evidencia_id y esa relación pertenece a version_id; propuesta solo con versión y debe pertenecer a ella; convocatoria solo para vínculo/publicación. Publicación aplicada exige propuesta y convocatoria; detalle incluye versión canónica resultante y diferencia aplicada. Actor administrador activo real validado al actuar. sustituye_id, si existe, debe ser anterior y del mismo objeto/dimensión/evidencia; un bloqueo transaccional impide decisiones vigentes divergentes. El historial nunca se elimina. Índices en objetos/dimensión/creada_en.

Nueva respecto v0.6. No modificar AUD_EVENTO actual: su implementación exige actor y convocatoria o institución; no sirve para un PDF sin convocatoria. Al aplicar una integración manual, crear esta revisión y AUD_EVENTO de negocio en la misma transacción, con el mismo administrador real. Ejecución automática solo crea ejecución/observación/acceso/incidencia, **no** revisiones con usuario ficticio. Publicación automática queda fuera del primer bloque; requerirá diseñar su auditoría de sistema sin falsificar actor humano antes de habilitarla. Aprobar fuente no aprueba todos los documentos que produzca.

## Consistencia, concurrencia y archivos

Orden propuesto: crear ejecución durable → obtener exclusión por fuente → descargar fuera de transacciones largas → persistir intento y documento → bloquear identidad de publicación → resolver versión/manifiesto → insertar observación → cerrar ejecución. UNIQUE evita carreras en insert; tras IntegrityError recuperar fila ganadora y comprobar igualdad íntegra. No mantener transacción durante DNS/HTTP/PDF. Una única ejecución activa por fuente, incluido modo manual, y exclusión por origen de red para fuentes que compartan host. La implementación futura combinará bloqueo asesor de sesión con estado en BD; el fallecimiento del trabajador libera el bloqueo y deja ejecución recuperable. No declarar abandonada por mero timeout: un recuperador obtiene primero exclusión, cierra con incidencia y nunca cambia datos públicos.

Escribir archivo temporal limitado en raíz privada, calcular/verificar hash, renombrar atómicamente al destino derivado, y solo entonces confirmar referencia BD. Error antes de commit puede dejar archivo huérfano: inventariar y señalar, **no borrar automáticamente**. Error de disco interrumpe la observación; no confirmar una evidencia inexistente. Respaldo consistente de PostgreSQL + directorio documental + manifiesto de hashes y versiones de extractor/configuración. Probar restauración y hashes; no asumir que el respaldo PostgreSQL existente incluye archivos nuevos.

Raíz propuesta configurable `RASTREO_STORAGE_ROOT`, absoluta fuera del repositorio y del directorio servido por Vite/Django. No usar outputs/rastreo (salida temporal actual) como archivo histórico definitivo. Permisos de SO limitados al proceso/administración; servir descargas autenticadas como adjuntos, nunca HTML ejecutable. Sin cambios actuales de credenciales o permisos. Ubicación/capacidad y retención deben acordarse; no se prescribe caducidad ni limpieza automática de evidencia.

## Fechas y beneficios: contrato para futura integración

En datos_extraidos versionados: cada fecha guarda original, evidencia exacta/localizador, precision (dia/instante/desconocida), dia date?, hora time?, zona varchar(64)?, instante timestamptz?. Para dia: día obligatorio, hora/zona/instante nulos. Instante requiere zona/offset publicado inequívoco y valor reproducible. Fecha ambigua conserva original sin inventar componentes. Consulta, publicación, apertura y cierre son conceptos distintos. Día posterior al cierre puede señalar vencida; durante el día de cierre no inferir 00:00 ni 23:59:59. Permanencia exige evidencia explícita.

Futura ampliación de MAE_CONVOCATORIA propuesta, **no realizada**: campos separados de precisión y día para apertura/cierre, o entidad temporal asociada si se aprueba; conservar DateTime actual únicamente para instantes conocidos, cierre_original y datos anteriores sin reinterpretarlos. El usuario debe aprobar semántica de integración y comportamiento durante el día de cierre antes de tocar el catálogo.

Beneficio observado: concepto original, porcentaje numeric(5,2)?, monto_fijo numeric(12,2)?, tope_monto numeric(12,2)?, moneda char(3)?, moneda_original text?, periodicidad, ámbito común/opción pendiente y condiciones text. CHECK cantidades >= 0, porcentaje 0–100. Ausencia no equivale a cero. Para $3000: tope literal conservado, código de moneda desconocido hasta revisión. 100 % matrícula/aranceles + tope no es 100 % de gastos ni una concesión fija. Futura adición de tope_monto a MAE_BENEFICIO y contrato de moneda/ámbito requiere aprobación y migración independiente; monto actual no se convierte retrospectivamente en tope. El contrato provisional puede conservar números con moneda desconocida, pero no cumple el contrato de inserción de monto monetario del modelo actual.

## Flujo con ejemplo y estados separados

Productivo: ejecución E1 descarga HTML H1/PDF P1; crea identidad SIAU+URL, documentos, versión V1 con extractor identificado, relaciones y observación E1→V1. convocatoria_id nulo. Conserva expresión maestrías tecnológicas, tope literal y cierre por día; nada se publica. Administrador revisa extracción de V1, admisibilidad del ministerio con evidencia explícita y documentación P1 (REL exacta) en decisiones distintas. Solo después propone vincular una canónica existente o crear borrador mediante servicios actuales, con datos suficientes y mapeos aprobados. Si faltan moneda, modalidad/nivel o precisión temporal, integración pendiente: no llenar huecos con datos ficticios. Esta fuente concreta está vencida; no entra en publicación automática de abiertas. Crear/vincular y publicar son acciones diferentes.

E2 sin cambios registra accesos y observación apuntando a V1. E3 devuelve H2 y P2: nueva versión V2 aun con título idéntico. P1 aprobado no aprueba P2. Se prepara propuesta contra versión canónica C7 y snapshot exacto; C7 sigue público. El administrador revisa diferencias y correcciones manuales. Al aplicar, bloquear canónica y publicación y comprobar versión **y hash del snapshot completo con relaciones** (no confiar solo en contador). Si ahora es C8 o difiere snapshot, propuesta obsoleta: regenerar y revisar; no sobreescribir. Aplicación válida actualiza campos explícitamente aprobados, registra auditoría y versión resultante en una transacción. Campos corregidos manualmente se preservan salvo decisión humana expresa motivada.

Cinco ejes independientes:

- Extracción: completa/parcial/fallida; describe calidad técnica.
- Oferente: pendiente/admisible/no admisible, decisión de revisión con evidencia; aparecer en SIAU no basta.
- Documentación: pendiente/aprobada/rechazada por versión/documento; revisión editorial de bases, no certificación de documentos del postulante.
- Publicación: conserva controles actuales de revisión/activación; ninguna descarga la activa por sí sola.
- Vigencia: próxima/abierta/cerrada/desconocida según fechas y precisión; cerrada no es rechazada. Un 404 genera incidencia, no pausa, borrado ni cancelación.

## Decisiones y bloques pequeños

Ya aprobados: mantener publicación/correcciones ante cambios; incidencia sin cancelación; cerradas conservadas por filtro/favoritos y fuera de abiertas por defecto. No se reabre aprobación ni se implementa ese filtro en esta tarea.

Requieren aprobación real: este suplemento estructural al v0.6 (incluidas FK opcionales y tablas nuevas); integración de precisión temporal sin instante inventado; tope económico y moneda con evidencia; nuevos mapeos académicos antes de crear opciones; ubicación/capacidad de archivo y política de retención si se desea alguna; representación de convenios antes de integrarlos. No hace falta pedir una decisión para corregir regex, instrumentar tiempos o añadir pruebas. No se propone una política automática de eliminación. Criterios de admisibilidad ya aprobados no se amplían; falta representar su evidencia.

1. **Primer bloque implementable tras aprobación del diseño:** CFG_FUENTE, TRA_EJECUCION_RASTREO, TEC_DOCUMENTO_RASTREO, TRA_ACCESO_RASTREO y TRA_INCIDENCIA_RASTREO con FKs a publicación/versión diferidas al bloque 2. Persistencia solo de acceso/evidencia, fuente desactivada y no aprobada inicialmente; sin canónicas, interfaz de publicación ni cron. Pruebas PostgreSQL test_becanexo_db --keepdb: duplicados/concurrencia, reintentos, robots, fallo de disco/rollback, ausencia de modificaciones de negocio y respaldo/restauración de archivos. Migración para revisión antes de aplicar.
2. Identidad, versiones, relaciones y observación; completar FKs diferidas e integridad. Probar repetición sin cambios, HTML cosmético, PDF cambiado, extractor nuevo, A→B→A y fallos parciales; no aprobación heredada.
3. Revisiones y propuestas, permisos/CSRF, actor real e interfaz administrativa; evidencias exactas, estados independientes y decisiones obsoletas concurrentes. Aún no publicación automática.
4. Tras aprobar integración temporal/económica y mapeos, vínculo/creación/edición mediante servicios de negocio, snapshot y auditoría. Probar conservación de correcciones y versión pública; catálogo y cerradas en bloque separado.
5. Solo después planificador, incidencias recuperables, política aprobada de publicación automática y su auditoría de sistema. Sin IA, similitud de títulos como identidad ni login PUSAK.

La tarea inicial de diseño entregó únicamente esta propuesta y correcciones del adaptador, sin tablas. El bloque posterior autorizado ya implementó las seis indicadas al inicio; los bloques restantes siguen diferidos.

## Precisiones de la revisión final del diseño

- En TRA_EJECUCION_RASTREO, fuente_id es bigint NOT NULL. Los tres contadores de v0.6 (nuevas, duplicadas, actualizadas) se sustituyen por los contadores explícitos propuestos; no se mantienen con otro significado oculto.
- Las URLs indexadas tienen también CHECK octet_length(url_normalizada) <= 2048, para limitar bytes y no solo caracteres en índices compuestos. Una URL que exceda el límite se registra como incidencia con referencia segura, sin truncarla ni crear identidad equivocada. La normalización quita el fragmento; no convierte toda la ruta a minúsculas.
- Hash relevante excluye también vigencia calculada al consultar y avisos derivados únicamente del reloj. El cambio de fecha de consulta no crea una versión documental. Los errores de parser y datos ausentes sí forman parte del resultado versionado; su contrato debe ser determinista.
- En una carrera de invocaciones, el intento de crear en_curso usa savepoint; el perdedor recupera su transacción y registra una ejecución omitida con su propia clave. No pierde la invocación por una violación UNIQUE. No liberar un bloqueo de origen compartido hasta que ninguna petición de la ejecución pueda continuar.
- Para evitar cambios de fuente sin auditoría en el bloque 1, incluir el subconjunto de AUD_REVISION_RASTREO para configuración/incidencias, administrador y clave de acción. Las columnas y FK de versión/evidencia/propuesta se incorporan en los bloques posteriores antes de habilitar esas dimensiones. El bloque 3 completa revisión de extracción/documentos y su interfaz; no inaugura tardíamente la auditoría de fuentes. La aprobación automática queda falsa durante los primeros bloques.
- Inmutabilidad de versión significa después de confirmar su transacción de inserción con todas sus relaciones; no requiere un estado mutable de aprobación en la versión. Las decisiones viven en auditoría. Una propuesta de cambios no puede ser aplicada dos veces: bloquear propuesta y comprobar la revisión aplicada existente; añadir UNIQUE parcial (propuesta_id) para dimension=publicacion y decision=aplicada. Una creación y su vínculo canónico se confirman juntos.
- Las reglas de publicación automática ya aprobadas siguen siendo necesarias, nunca suficientes por un booleano de fuente: oferente admisible, información mínima, opciones fiables, vigencia/permanencia explícita y ausencia de conflictos. La auditoría de publicación automática sigue pendiente de diseño antes de habilitarla.
