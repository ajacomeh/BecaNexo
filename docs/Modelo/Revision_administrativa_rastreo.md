# Suplemento: revisión administrativa de rastreo

Implementado el 29/10/2026. Complementa los bloques 1 y 2; conserva el JSON v0.6 histórico. No crea tablas ni modifica el catálogo. Migraciones: `0006_revision_editorial` (depende de 0005) y `0007_integridad_revision_editorial` (depende de 0006). Aplicadas en test_becanexo_db y becanexo_db; evidencia de respaldo y pruebas en avance.md.

## Ampliación de AUD_REVISION_RASTREO

| Campo nuevo | PostgreSQL | Nulabilidad / relación |
| --- | --- | --- |
| version_id | bigint | NULL; FK a TRA_VERSION_PUBLICACION |
| evidencia_id | bigint | NULL; FK a REL_VERSION_DOCUMENTO, no al documento físico |

FK con índice, Django PROTECT y PostgreSQL NO ACTION diferible. Los demás campos permanecen: actor, creada_en, fuente, incidencia, dimension, decision, motivo, detalle, clave_accion, sustituye y transaccion_id. Ninguna fila histórica se rellena o reinterpreta; las dos nuevas columnas quedan NULL en las revisiones anteriores.

La restricción de objeto se amplía: configuración exige fuente; incidencia exige incidencia; extracción/documental/oferente exigen versión. Son objetos principales excluyentes. Fuente y publicación de una revisión editorial se deducen de su versión inmutable; no se aceptan del cliente. Extracción no lleva evidencia individual; documental y oferente requieren una relación documental perteneciente exactamente a la versión.

Se reutilizan las decisiones `pendiente`, `aprobada`, `rechazada`. `aplicada` y `resuelta` no se admiten para estas tres dimensiones. La ausencia de filas significa información pendiente, no una decisión atribuida a un administrador. Vigencia, aprobación de fuente, calidad técnica y publicación son conceptos independientes.

| Dimensión | Alcance de una aprobación |
| --- | --- |
| extraccion | La información extraída representa fielmente la evidencia de esa versión; no acredita elegibilidad ni vigencia |
| documental | Revisión editorial del documento exacto de esa versión; no certifica documentos del postulante ni resuelve incidencias |
| oferente | Admisibilidad de una entidad ecuatoriana respaldada por evidencia examinada; no publica la oferta |

Para oferente, `detalle` conserva `tipo_oferente` (entidad_ecuatoriana/convenio/no_determinado) y `referencia` textual obligatoria a la evidencia. La API limita referencia a 2000 caracteres y motivo a 5000, recorta espacios, exige texto y rechaza campos adicionales. Convenio/no_determinado no pueden aprobarse. El formulario no representa todavía la evidencia estructurada de participación formal de convenios; no se amplía su admisibilidad por aparecer en una fuente ecuatoriana.

## Historial, duplicados y concurrencia

- Actor exclusivamente de la sesión; administrador activo validado de nuevo bajo bloqueo. La fecha se genera en el servidor y el trigger sella el instante de inserción. No se reciben actor/fecha del cliente.
- La revisión es también su registro de auditoría: una única inserción transaccional. No existe otra tabla duplicada ni actualización de un estado mutable en versiones/documentos.
- Rectificar exige `sustituye_id` de la decisión vigente. La nueva fila conserva versión, dimensión y evidencia de la anterior; no cambia ni elimina la anterior. En oferente la cadena corresponde a una dimensión por versión, y mantiene la evidencia elegida inicialmente. Cambiar su evidencia requerirá un diseño explícito de sustitución distinto; no se fuerza editando el historial.
- UNIQUE parcial para una raíz por versión/dimensión (extracción, oferente), una raíz por versión/evidencia (documental) y un único sucesor editorial por revisión. Trigger comprueba pertenencia y sustitución del mismo objeto/dimensión/evidencia. Se conservan los triggers previos de inmutabilidad, incluso para UPDATE/DELETE directos.
- UUID `clave_accion` único global. Mismo actor, versión y contenido con la misma clave devuelve la fila existente (200); reutilización con otro contenido devuelve 409. Nueva decisión devuelve 201. La interfaz conserva la clave para reintentar el mismo envío; cambios del contenido generan otra clave.
- Bloqueo de usuario, bloqueo asesor transaccional de clave y bloqueo de versión serializan la escritura. Dos administradores que parten de la misma revisión no se sobrescriben: uno registra y el otro recibe 409. Debe actualizar el historial y confirmar nuevamente, conservando su texto.
- Decisiones vigentes se calculan excluyendo revisiones sustituidas. Se calculan por versión y documento exactos; un PDF compartido no hereda aprobación en otra versión. A→B→A vuelve a A y sus decisiones propias: no copia decisiones de B.

## Límites

No existen propuestas de cambio, vínculos con convocatorias, publicación, resolución de incidencias, planificación diaria, IA o nuevas descargas. Se conservan `rast_fuente_no_auto` y `rast_publicacion_sin_vinculo`. Las revisiones de configuración previas y su auditoría transaccional no se alteran. La migración reemplaza únicamente el CHECK de objeto por su ampliación; no elimina columnas, tablas ni datos. La reversión no es una operación autorizada de esta tarea y requeriría revisar las filas editoriales existentes.
