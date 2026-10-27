# Suplemento implementado: rastreo, bloque 1

Fecha: 27/10/2026. El modelo lógico v0.6 JSON se conserva histórico, sin reescritura. Este suplemento describe seis tablas nuevas implementadas por rastreo.0001_initial y las garantías PostgreSQL de 0002_integridad_historial, aplicadas en pruebas y desarrollo.

No implementa publicaciones detectadas, versiones, propuestas ni relaciones futuras. No cambia MAE_CONVOCATORIA, fechas, beneficios ni AUD_EVENTO existente. No hay publicación automática ni planificación diaria.

Todos los id son bigint identity PK. Las FK usan Django PROTECT y FK PostgreSQL NO ACTION diferibles (sin cascadas destructivas); no confundir con un ON DELETE RESTRICT literal. Los triggers de historial también impiden eliminación. Índices de FK y UNIQUE creados por migración.

## CFG_FUENTE

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| nombre | varchar(160) | No |  |
| tipo | varchar(12) | No |  |
| adaptador | varchar(100) | No |  |
| url_base | text | No | UNIQUE |
| frecuencia_min | integer | No |  |
| espera_seg | integer | No |  |
| timeout_seg | integer | No |  |
| activa | boolean | No |  |
| aprobada_publicacion_automatica | boolean | No |  |
| politica_acceso | jsonb | No |  |
| politica_version | varchar(60) | No |  |
| creada_en | timestamp with time zone | No |  |

Restricciones declaradas: `rast_fuente_no_auto`, `rast_fuente_limites`, `rast_fuente_tipo`.

## TRA_EJECUCION_RASTREO

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| fuente_id | bigint | No | FK → CFG_FUENTE.id; PROTECT |
| clave_idempotencia | uuid | No | UNIQUE |
| origen | varchar(16) | No |  |
| solicitado_por_id | bigint | Sí | FK → MAE_USUARIO.id; PROTECT |
| inicio | timestamp with time zone | No |  |
| fin | timestamp with time zone | Sí |  |
| estado | varchar(20) | No |  |
| configuracion_snapshot | jsonb | No |  |
| version_extractor | varchar(80) | No |  |
| version_normalizador | varchar(60) | No |  |
| latido_en | timestamp with time zone | Sí |  |
| publicaciones_observadas | integer | No |  |
| versiones_nuevas | integer | No |  |
| observaciones_sin_cambios | integer | No |  |
| error_resumen | text | Sí |  |

Restricciones declaradas: `rast_una_activa`, `rast_ejec_actor`, `rast_ejec_estado`, `rast_ejec_fechas`, `rast_ejec_sin_publicaciones`.

## TEC_DOCUMENTO_RASTREO

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| sha256 | varchar(64) | No | UNIQUE |
| tamano_bytes | bigint | No |  |
| mime | varchar(100) | No |  |
| clave_almacenamiento | varchar(180) | No | UNIQUE |
| creado_en | timestamp with time zone | No |  |

Restricciones declaradas: `rast_doc_hash`, `rast_doc_mime`, `rast_doc_tamano`.

## TRA_ACCESO_RASTREO

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| ejecucion_id | bigint | No | FK → TRA_EJECUCION_RASTREO.id; PROTECT |
| documento_id | bigint | Sí | FK → TEC_DOCUMENTO_RASTREO.id; PROTECT |
| secuencia | integer | No |  |
| rol | varchar(20) | No |  |
| url_original | text | No |  |
| url_normalizada | varchar(2048) | No |  |
| url_final | text | Sí |  |
| admitido_en | timestamp with time zone | No |  |
| inicio_peticion_en | timestamp with time zone | Sí |  |
| fin | timestamp with time zone | No |  |
| espera_ms | bigint | No |  |
| duracion_ms | bigint | Sí |  |
| http_status | smallint | Sí |  |
| resultado | varchar(20) | No |  |
| error_codigo | varchar(60) | Sí |  |
| etag | text | Sí |  |
| last_modified | text | Sí |  |

Restricciones declaradas: `rast_acceso_secuencia`, `rast_acceso_seq_positivo`, `rast_acceso_rol`, `rast_acceso_http`, `rast_acceso_resultado`, `rast_acceso_fechas`.

## TRA_INCIDENCIA_RASTREO

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| fuente_id | bigint | No | FK → CFG_FUENTE.id; PROTECT |
| ejecucion_id | bigint | Sí | FK → TRA_EJECUCION_RASTREO.id; PROTECT |
| acceso_id | bigint | Sí | FK → TRA_ACCESO_RASTREO.id; PROTECT |
| codigo | varchar(60) | No |  |
| gravedad | varchar(12) | No |  |
| detalle | text | No |  |
| detectada_en | timestamp with time zone | No |  |
| clave_evento | uuid | No | UNIQUE |

Restricciones declaradas: `rast_incid_gravedad`, `rast_incid_acceso_ejec`.

## AUD_REVISION_RASTREO

| Campo | Tipo PostgreSQL | NULL | Clave / relación |
| --- | --- | --- | --- |
| id | bigint | No | PK |
| actor_id | bigint | No | FK → MAE_USUARIO.id; PROTECT |
| creada_en | timestamp with time zone | No |  |
| fuente_id | bigint | Sí | FK → CFG_FUENTE.id; PROTECT |
| incidencia_id | bigint | Sí | FK → TRA_INCIDENCIA_RASTREO.id; PROTECT |
| dimension | varchar(24) | No |  |
| decision | varchar(24) | No |  |
| motivo | text | No |  |
| detalle | jsonb | No |  |
| clave_accion | uuid | No | UNIQUE |
| sustituye_id | bigint | Sí | FK → AUD_REVISION_RASTREO.id; PROTECT |
| transaccion_id | bigint | No |  |

Restricciones declaradas: `rast_revision_objeto`, `rast_revision_decision`, `rast_revision_motivo`.

## Reglas y diferencias respecto al ER v0.6

- CFG_FUENTE reutiliza nombre/campos previstos, añade política JSON cerrada, versión de política y creada_en. Activa inicia false. Aprobación automática tiene CHECK false y no existe servicio para habilitarla. Espera mínima 2 s y timeout máximo 15 s conservan el descargador actual; configuración auditada con antes/después y actor administrador activo.
- TRA_EJECUCION_RASTREO añade UUID idempotente, origen, actor manual nullable solo para origen programada reservado, snapshot y versiones, latido y contadores explícitos. Solo una en_curso por fuente. Contadores de publicaciones/versiones/observaciones están restringidos a cero porque su persistencia está diferida. Resumen calcula accesos/documentos aparte. No se programa ninguna ejecución.
- TEC_DOCUMENTO_RASTREO nueva: SHA-256 varchar(64) validado hexadecimal, tamaño, MIME y clave privada. Django usa varchar y no char fijo; semántica de huella conservada. Servicio verifica bytes y sistema de archivos antes de insertar referencia. PDF <= 8 MiB, texto <= 2 MiB; CHECK global máximo 8 MiB y validación específica por MIME en servicio.
- TRA_ACCESO_RASTREO nueva: un registro por intento/salto de red, secuencia única por ejecución, documento opcional solo en errores/bloqueos/redirecciones. Añadido resultado redirigido para HTTP 3xx sin documento, además de descargado/reutilizado/bloqueado/error. Solo puede insertarse sobre ejecución en_curso. El módulo actual no envía peticiones condicionales 304: reutilizado significa mismos bytes SHA-256, no recepción de 304.
- TRA_INCIDENCIA_RASTREO nueva, fuente obligatoria, ejecución/acceso opcionales coherentes comprobados por trigger. Sin publicación ni versión todavía. 404/timeout/cambio de PDF solo generan incidencias, nunca modifican convocatorias.
- AUD_REVISION_RASTREO nueva: solo configuración o incidencia con XOR, motivo, administrador real y antes/después. transaccion_id es campo técnico adicional (txid_current sellado por trigger) para comprobar auditoría de configuración en la misma transacción; no es identidad de usuario ni sesión. Sustitución solo del mismo objeto/dimensión. Las dimensiones de extracción/documentos/publicación y sus FKs siguen diferidas.

## Protección de historial y servicios

Triggers BEFORE rechazan UPDATE/DELETE de documentos, accesos, incidencias y revisiones incluso si se omite save(). Ejecuciones finales no se modifican/eliminan; mientras están en_curso solo pueden variar cierre, estado, latido y error_resumen; no pueden pasar a omitida. CHECK coordina fin/estado y fechas. Fuente no se elimina y cualquier INSERT/UPDATE requiere auditoría exacta al commit mediante constraint trigger diferido. No se añadieron formularios genéricos en Admin.

La CLI valida administrador activo y los triggers vuelven a validar actor. Los locks de sesión PostgreSQL coordinan origen y fuente sin mantener transacciones abiertas durante red/archivos. Las relaciones diferidas se añadirán únicamente cuando existan publicaciones/versiones/propuestas; no se insertan filas ficticias.

Guías: [comandos](../comandos-rastreo.md), [respaldo conjunto](../respaldo-rastreo.md), [diseño futuro](../propuesta-persistencia-rastreo.md).
