# Suplemento implementado: rastreo, bloque 2

Complementa v0.6 y [bloque 1](Persistencia_rastreo_bloque1.md); no reemplaza los JSON históricos. Migraciones aditivas: `0003_publicaciones_versiones`, `0004_integridad_versiones`, `0005_coherencia_observaciones`. El resultado de su aplicación en cada entorno se registra en avance.md.

Todas las tablas tienen `id bigint identity PRIMARY KEY`. Todos los campos son NOT NULL salvo los marcados **NULL**. FK con Django PROTECT y PostgreSQL NO ACTION diferible, sin cascadas. Los triggers impiden editar/eliminar versiones, relaciones y observaciones. Fechas `timestamp with time zone`; almacenamiento UTC. Las huellas son `varchar(64)` con CHECK hexadecimal minúsculo, coherente con el bloque 1.

## TRA_PUBLICACION_FUENTE

| Campo | Tipo / nulabilidad | Relación o significado |
| --- | --- | --- |
| fuente_id | bigint | CFG_FUENTE |
| convocatoria_id | bigint **NULL** | MAE_CONVOCATORIA; CHECK IS NULL durante este bloque |
| url_original | text | Primera URL observada; no sustituir por destino de redirección |
| url_normalizada | varchar(2048) | Identidad dentro de la fuente |
| normalizacion_version | varchar(60) | `urls-cerradas/1` |
| primera_deteccion, ultima_deteccion | timestamptz | Primera evidencia HTML conservada y última observación con contenido |

UNIQUE(fuente_id,url_normalizada); CHECK última >= primera y URL entre 1 y 2048 bytes. Identidad inmutable, salvo avance de última detección. No hay vinculación habilitada ni borrado. El servicio crea la identidad al conservar correctamente el HTML; un fallo inicial de una ficha desconocida solo produce acceso/incidencia. Los fallos posteriores sobre una conocida añaden observación sin versión.

Normalización actual: HTTPS, host en minúsculas, elimina puerto 443 y fragmento; conserva ruta, mayúsculas, escapes y barra final. **Este adaptador cerrado no admite parámetros de consulta**, credenciales ni espacios; no los elimina silenciosamente. Una futura fuente que necesite parámetros requiere contrato nuevo explícito y revisión de sensibilidad. No se truncan URLs. Documento, título y URL final de una redirección no fusionan identidades. El mismo URL de fuentes distintas representa publicaciones distintas.

## TRA_VERSION_PUBLICACION

| Campo | Tipo / nulabilidad | Significado |
| --- | --- | --- |
| publicacion_id | bigint | TRA_PUBLICACION_FUENTE |
| numero | integer > 0 | Secuencia de nuevas versiones por identidad, bajo bloqueo |
| creada_en | timestamptz | Confirmación de interpretación nueva, no fecha de publicación |
| version_extractor | varchar(80) | Versión del código extractor de la ejecución |
| version_normalizador | varchar(60) | Versión del contrato URL |
| version_contrato | integer > 0 | Contrato de serialización, inicialmente 1 |
| hash_manifiesto, hash_contenido_relevante | varchar(64) | SHA-256 de serialización determinista |
| manifiesto | jsonb | Documentos exactos y enlaces pendientes con estado |
| datos_extraidos | jsonb | Datos originales y estructuración conservadora, sin opciones ni mapeos nuevos |
| texto_extraido | text **NULL** | Texto de la sección de ficha, no menú/pie/scripts |
| advertencias | jsonb | Incertidumbres estructurales/documentales; sin avisos derivados del reloj |
| estado_extraccion | varchar(20) | completa/parcial/fallida; no estado editorial |
| transaccion_id | bigint | Sello técnico asignado por PostgreSQL mediante txid_current() |

UNIQUE(publicacion_id,numero). UNIQUE(publicacion_id,hash_manifiesto,version_extractor,version_normalizador,version_contrato). No aprobación almacenada/heredada. `manifiesto` y `transaccion_id` son ajustes técnicos explícitos frente al borrador: el manifiesto necesita conservarse, no solo su huella; el sello impide anexar evidencias en transacciones posteriores, incluso por ORM directo.

Manifest: `documentos` ordenados por rol/URL, cada uno con rol, URL normalizada y SHA-256; `pendientes` ordenados por URL/estado (inaccesible/fuera_de_lista). Sin timestamps. Hash relevante: datos, texto pertinente y advertencias; excluye bytes/hash HTML, hora de consulta, vigencia calculada y versión del extractor. La identidad del extractor sí participa en la clave de versión. No elimina negaciones, acentos ni condiciones. Porciones del HTML fuera de la ficha no cambian el contenido relevante.

Un cambio de PDF modifica manifiesto y clasificación de cambio aunque el texto no se extraiga: no equivale a aprobación documental. Un fallo de PDF produce versión parcial con HTML válido y enlace pendiente; no toma un PDF antiguo como si se hubiera obtenido en esa ejecución. Las versiones nuevas se confirman junto con relaciones y observación. Un resultado no determinista para la misma evidencia/contrato se rechaza y deja incidencia, en lugar de sobrescribirlo.

## REL_VERSION_DOCUMENTO

| Campo | Tipo / nulabilidad | Relación o significado |
| --- | --- | --- |
| version_id | bigint | TRA_VERSION_PUBLICACION |
| documento_id | bigint | TEC_DOCUMENTO_RASTREO |
| rol | varchar(20) | ficha_html/bases_pdf/anexo |
| url_original | text | URL original de ficha o href de bases |
| url_normalizada | varchar(2048) | URL resuelta sin truncamiento, límite 2048 bytes |
| localizador | text **NULL** | Referencia de sección si existe |

UNIQUE(version_id,rol,url_normalizada). MIME coherente con ficha_html/bases_pdf. Documento puede ser compartido físicamente por varias publicaciones/versiones sin fusionarlas. Inserción solo dentro de la transacción de creación de versión; posterior modificación, eliminación o anexado rechazada. Trigger diferido comprueba que el manifiesto coincida con el conjunto exacto de relaciones y exista HTML. No se requiere añadir parejas UNIQUE(id,publicacion_id) como en la propuesta inicial: se aplica pertenencia mediante triggers PostgreSQL, no mediante FK compuesta del ORM.

## TRA_OBSERVACION_RASTREO

| Campo | Tipo / nulabilidad | Relación o significado |
| --- | --- | --- |
| ejecucion_id | bigint | TRA_EJECUCION_RASTREO |
| publicacion_id | bigint | TRA_PUBLICACION_FUENTE |
| version_id | bigint **NULL** | TRA_VERSION_PUBLICACION; NULL únicamente en fallo |
| observada_en | timestamptz | Orden temporal de consultas; se desempata por id |
| resultado | varchar(24) | nueva/sin_cambios/cambio_bytes/cambio_relevante/fallo |
| detalle | text **NULL** | Explicación técnica segura |

UNIQUE(ejecucion_id,publicacion_id); índice(publicacion_id,observada_en). Trigger comprueba fuente común, ejecución activa y versión de esa publicación. La evidencia de una observación exitosa debe constar en accesos de esa ejecución; no se puede atribuir un documento histórico no obtenido. A→B→A reutiliza A sin perder cronología. `sin_cambios` significa misma versión que la última observación exitosa; `cambio_bytes` indica versión distinta sin cambio relevante detectado ni PDF distinto (incluye reinterpretación con contrato/extractor nuevo sin diferencia semántica detectada). CLI muestra ambos números de extractor y manifiestos para no confundirlo con un cambio semántico comprobado.

## Relaciones y garantías añadidas al bloque 1

- TRA_ACCESO_RASTREO: `publicacion_id bigint NULL`, FK a identidad. Robots e índice quedan sin publicación. Una primera redirección/fallo sin identidad conocida puede quedar sin relación; no se reescribe después. PDFs compartidos pueden descargarse una sola vez por ejecución y servir como evidencia exacta de ambas versiones; su acceso conserva el contexto original de descarga.
- TRA_INCIDENCIA_RASTREO: `publicacion_id bigint NULL`, `version_id bigint NULL`. Fuente/ejecución/acceso/publicación/versión deben ser coherentes. Los errores previos a confirmar versión no reciben un vínculo ficticio. Todas las FK nuevas de registros históricos conservan NULL.
- Contadores de ejecución ya no están restringidos a cero. `publicaciones_observadas` cuenta observaciones, incluidas fallidas sobre identidades conocidas; `versiones_nuevas` cuenta primeras observaciones de versiones nuevas; `observaciones_sin_cambios` cuenta resultado sin_cambios. Trigger diferido contrasta contadores con filas reales; actualizaciones permitidas solo mientras en_curso. Finalizadas permanecen inmutables. No cuentan convocatorias creadas/publicadas.
- Bloqueo de identidad para numeración/reutilización; UNIQUE protege carreras de creación. Exclusión por fuente/origen, claves de ejecución y recuperación del bloque 1 conservadas. Red y archivos fuera de transacciones; metadatos/versiones en transacciones cortas.

## Diferencias frente a v0.6 y alcance pendiente

En v0.6 TRA_PUBLICACION_FUENTE exigía convocatoria y ejecución y almacenaba hash/texto mutable. Ahora la convocatoria es opcional y por el momento obligatoriamente NULL; ejecución vive en observación y hash/texto en versión inmutable. Se incorporan las otras tres tablas y relaciones opcionales de contexto, sin rellenar retrospectivamente el historial. No se modifica AUD_EVENTO, catálogo, fechas de convocatoria, beneficios, perfiles o usuarios.

No se implementan TRA_PROPUESTA_CAMBIO ni revisión editorial de versiones/documentos, vínculo/creación de convocatorias, publicación automática, convenios, conversión académica/monetaria/temporal, IA, frontend ni planificación diaria. La revisión documental continúa pendiente incluso con descarga y extracción completas.
