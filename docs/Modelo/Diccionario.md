# BecaNexo · Diccionario lógico v0.6
Base v0.5 con ampliación de comparación del 26/10/2026. Modelo parcialmente implementado; el avance distingue tablas existentes de las futuras. No contiene SQL. PK primero, FK después y atributos del negocio. Véase Ampliacion_comparacion_v06.md para contratos y diferencias respecto al ER histórico.

## Ampliación implementada de rastreo — 27/10/2026

El JSON Modelo_logico_v06.json se conserva histórico. Las definiciones v0.6 de este documento no se reescriben silenciosamente: el [suplemento Persistencia_rastreo_bloque1.md](Persistencia_rastreo_bloque1.md) especifica **todos los campos, tipos SQL, nulabilidad, claves y reglas efectivos** de las seis tablas implementadas por rastreo.0001/0002.

| Tabla existente tras el bloque 1 | Finalidad y diferencia frente a v0.6 |
| --- | --- |
| CFG_FUENTE | Configuración auditada, política cerrada y activación separada de aprobación automática (CHECK false) |
| TRA_EJECUCION_RASTREO | Invocación UUID, actor manual real, snapshot, estados y contadores de publicación restringidos a cero |
| TEC_DOCUMENTO_RASTREO | Nueva; huella/tamaño/MIME/clave de archivo privado, inmutable |
| TRA_ACCESO_RASTREO | Nueva; intento de red con tiempos, HTTP y documento opcional según resultado; incluye redirigido |
| TRA_INCIDENCIA_RASTREO | Nueva; fuente/ejecución/acceso coherentes, sin usuario o convocatoria ficticios |
| AUD_REVISION_RASTREO | Nueva; solo configuración/incidencias, administrador real, antes/después y sello técnico transaccion_id |

La tabla anterior describe el cierre del bloque 1. El **bloque 2** añade TRA_PUBLICACION_FUENTE (sin vínculo canónico habilitado), TRA_VERSION_PUBLICACION, REL_VERSION_DOCUMENTO y TRA_OBSERVACION_RASTREO; relaciones opcionales de contexto en accesos/incidencias, y contadores reales de observaciones/versiones. Véase [Persistencia_rastreo_bloque2.md](Persistencia_rastreo_bloque2.md) para campos, tipos, nulabilidad, claves, ajustes y garantías efectivos. Propuestas y revisión editorial completa siguen pendientes. AUD_EVENTO existente no cambió. PostgreSQL impide mutación del historial incluso mediante ORM que omita save; FK SQL NO ACTION diferibles y Django PROTECT, sin cascadas destructivas. No se cambian campos de convocatorias, beneficios ni perfiles. Los suplementos efectivos prevalecen para el estado implementado; las definiciones históricas que siguen se conservan como referencia.

## CAT_PAIS
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| codigo | char(2) |  / único | - | Obligatorio. Código ISO de dos letras. |
| nombre | varchar(100) |  | - | Obligatorio. Nombre visible. |
## MAE_USUARIO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| email | varchar(254) |  / único | - | Obligatorio. Correo; único sin distinguir mayúsculas. |
| password_hash | varchar(128) |  | - | Obligatorio. Hash gestionado por Django; nunca contraseña en claro. |
| nombre | varchar(180) |  | - | Obligatorio. Nombre visible. |
| rol | varchar(20) |  | - | Obligatorio. postulante o administrador. |
| activo | boolean |  | - | Obligatorio. Permite desactivar la cuenta. |
| creado_en | timestamptz |  | - | Obligatorio. Fecha de alta. |
## MAE_PERFIL
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| usuario_id | bigint | FK / único | MAE_USUARIO.id | Obligatorio. Un perfil por cuenta. |
| nacionalidad_id | bigint | FK | CAT_PAIS.id | Obligatorio. Debe referenciar Ecuador (EC); regla del alcance. |
| residencia_id | bigint | FK | CAT_PAIS.id | Opcional; ausencia no implica incumplimiento. País de residencia. |
| fecha_nacimiento | date |  | - | Opcional; ausencia no implica incumplimiento. Opcional; solo si es necesaria para requisitos de edad. |
| version | integer |  | - | Obligatorio. Aumenta al modificar datos del perfil o sus relaciones. |
| actualizado_en | timestamptz |  | - | Obligatorio. Última modificación. |
| provincia_residencia | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| ciudad_residencia | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| dedicacion_disponible | varchar(20) |  | - | Opcional; ausencia no implica incumplimiento. completa/parcial/ambas; NULL=sin declarar |
| disponible_traslado | boolean |  | - | Opcional; ausencia no implica incumplimiento. NULL=sin declarar; false=no |
| disponible_extranjero | boolean |  | - | Opcional; ausencia no implica incumplimiento. NULL=sin declarar; false=no |
## MAE_FORMACION
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Propietario de la formación. |
| nivel | varchar(30) |  | - | Obligatorio. bachillerato, grado, especializacion, maestria o doctorado. |
| carrera | varchar(200) |  | - | Obligatorio. Nombre de la carrera. |
| institucion | varchar(200) |  | - | Opcional; ausencia no implica incumplimiento. Institución donde estudió. |
| titulo_obtenido | boolean |  | - | Obligatorio. Distingue título obtenido de estudios en curso. |
| promedio | numeric(7,3) |  | - | Opcional; ausencia no implica incumplimiento. Promedio en escala original. |
| escala_min | numeric(7,3) |  | - | Opcional; ausencia no implica incumplimiento. Mínimo de la escala. |
| escala_max | numeric(7,3) |  | - | Opcional; ausencia no implica incumplimiento. Máximo de la escala. |
| estado_estudios | varchar(20) |  | - | Obligatorio. en_curso/concluidos |
| nombre_titulo | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| fecha_finalizacion | date |  | - | Opcional; ausencia no implica incumplimiento.  |
| area_id | bigint | FK | CAT_AREA.id | Opcional; ausencia no implica incumplimiento. Área del título declarado |
## CAT_IDIOMA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| codigo | varchar(12) |  / único | - | Obligatorio. Código del idioma. |
| nombre | varchar(80) |  | - | Obligatorio. Nombre visible. |
## REL_PERFIL_IDIOMA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Perfil del postulante. |
| idioma_id | bigint | FK | CAT_IDIOMA.id | Obligatorio. Idioma declarado. |
| nivel | varchar(2) |  | - | Opcional; ausencia no implica incumplimiento. Nivel MCER o desconocido. |
## CAT_AREA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| nombre | varchar(140) |  / único | - | Obligatorio. Área normalizada. |
## REL_PERFIL_AREA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Perfil interesado. |
| area_id | bigint | FK | CAT_AREA.id | Obligatorio. Área de interés. |
## CFG_PREFERENCIA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Perfil del postulante. |
| nivel | varchar(30) |  | - | Obligatorio. Nivel deseado. |
| modalidad | varchar(20) |  | - | Obligatorio. Modalidad aceptada. |
## REL_PERFIL_PAIS
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Perfil interesado. |
| pais_id | bigint | FK | CAT_PAIS.id | Obligatorio. Destino preferido. |
## MAE_INSTITUCION
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| nombre | varchar(200) |  | - | Obligatorio. Nombre oficial. |
| sector | varchar(12) |  | - | Obligatorio. Público o privado. |
| pais_id | bigint | FK | CAT_PAIS.id | Obligatorio. Debe referenciar Ecuador (EC); regla del alcance. |
| url_oficial | text |  | - | Opcional; ausencia no implica incumplimiento. Dirección institucional. |
## CFG_FUENTE
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| nombre | varchar(160) |  | - | Obligatorio. Nombre administrativo. |
| url_base | text |  / único | - | Obligatorio. URL validada contra destinos permitidos. |
| tipo | varchar(12) |  | - | Obligatorio. Público o privado. |
| adaptador | varchar(100) |  | - | Obligatorio. Identificador de código de extracción; no código ejecutable del usuario. |
| frecuencia_min | integer |  | - | Obligatorio. Intervalo entre revisiones. |
| espera_seg | integer |  | - | Obligatorio. Pausa entre peticiones. |
| timeout_seg | integer |  | - | Obligatorio. Tiempo máximo por petición. |
| activa | boolean |  | - | Obligatorio. Permite pausar el rastreo. |
## TRA_EJECUCION_RASTREO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| fuente_id | bigint | FK | CFG_FUENTE.id | Obligatorio. Fuente consultada. |
| inicio | timestamptz |  | - | Obligatorio. Inicio de la tarea. |
| fin | timestamptz |  | - | Opcional; ausencia no implica incumplimiento. Final de la tarea. |
| estado | varchar(20) |  | - | Obligatorio. en_curso, finalizada, fallida o parcial. |
| nuevas | integer |  | - | Obligatorio. Convocatorias nuevas. |
| duplicadas | integer |  | - | Obligatorio. Publicaciones ya conocidas. |
| actualizadas | integer |  | - | Obligatorio. Convocatorias modificadas. |
| error_resumen | text |  | - | Opcional; ausencia no implica incumplimiento. Mensaje saneado; sin credenciales. |
## MAE_CONVOCATORIA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| institucion_id | bigint | FK | MAE_INSTITUCION.id | Obligatorio. Oferente. |
| titulo | varchar(250) |  | - | Obligatorio. Título de la convocatoria. |
| descripcion | text |  | - | Obligatorio. Texto normalizado. |
| apertura | timestamptz |  | - | Opcional; ausencia no implica incumplimiento. Inicio si está publicado. |
| cierre | timestamptz |  | - | Opcional; ausencia no implica incumplimiento. Fecha interpretada con zona; nulo si no se conoce. |
| cierre_original | text |  | - | Opcional; ausencia no implica incumplimiento. Texto literal para revisar ambigüedades. |
| url_oficial | text |  | - | Obligatorio. URL final validada para postular. |
| clave_deduplicacion | char(64) |  / único | - | Obligatorio. SHA-256 de identidad canónica conservadora. |
| revision | varchar(16) |  | - | Obligatorio. Estado de validación humana. |
| activa | boolean |  | - | Obligatorio. Desactivación administrativa. |
| version | integer |  | - | Obligatorio. Versión de datos y requisitos. |
| actualizado_en | timestamptz |  | - | Obligatorio. Última actualización. |
| tipo_beca_id | bigint | FK | CAT_TIPO_BECA.id | Opcional; ausencia no implica incumplimiento.  |
| cobertura_tipo | varchar(20) |  | - | Opcional; ausencia no implica incumplimiento. total/parcial/mixta/no_especificada; resumen según bases |
| gastos_no_cubiertos | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| obligaciones_beneficiario | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| fecha_publicacion | date |  | - | Opcional; ausencia no implica incumplimiento.  |
| url_bases | text |  | - | Opcional; ausencia no implica incumplimiento.  |
## MAE_OPCION_ESTUDIO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Convocatoria propietaria. |
| nivel | varchar(30) |  | - | Obligatorio. Nivel de esta opción. |
| modalidad | varchar(20) |  | - | Obligatorio. Modalidad de esta opción. |
| activa | boolean |  | - | Obligatorio. Desactivar sin borrar resultados históricos. |
| programa | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| institucion_destino | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| inicio_estudios | date |  | - | Opcional; ausencia no implica incumplimiento.  |
| duracion_meses | integer |  | - | Opcional; ausencia no implica incumplimiento.  |
| cupos | integer |  | - | Opcional; ausencia no implica incumplimiento.  |
## REL_OPCION_ESTUDIO_PAIS
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| opcion_estudio_id | bigint | FK | MAE_OPCION_ESTUDIO.id | Obligatorio. Opción de nivel y modalidad. |
| pais_id | bigint | FK | CAT_PAIS.id | Obligatorio. País de destino confirmado. |
## TRA_PUBLICACION_FUENTE
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Convocatoria canónica. |
| fuente_id | bigint | FK | CFG_FUENTE.id | Obligatorio. Fuente donde se observó. |
| ejecucion_id | bigint | FK | TRA_EJECUCION_RASTREO.id | Obligatorio. Última ejecución que observó la publicación. |
| url_normalizada | text |  | - | Obligatorio. Identificador dentro de la fuente. |
| hash_contenido | char(64) |  | - | Obligatorio. Detecta cambios de contenido. |
| texto_extraido | text |  | - | Opcional; ausencia no implica incumplimiento. Evidencia mínima de la última extracción. |
| primera_deteccion | timestamptz |  | - | Obligatorio. Primera observación. |
| ultima_deteccion | timestamptz |  | - | Obligatorio. Última observación. |
## REL_CONVOCATORIA_AREA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Oferta. |
| area_id | bigint | FK | CAT_AREA.id | Obligatorio. Área académica. |
## MAE_REQUISITO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Oferta propietaria. |
| texto_original | text |  | - | Obligatorio. Condición tal como se publicó. |
| obligatorio | boolean |  | - | Obligatorio. Distingue requisito de preferencia. |
| operador | varchar(24) |  | - | Opcional; ausencia no implica incumplimiento. Operador de una lista permitida en el backend. |
| valor_estructurado | jsonb |  | - | Opcional; ausencia no implica incumplimiento. Valor tipado según esquema validado para cada tipo. |
| validado | boolean |  | - | Obligatorio. Regla revisada antes de automatizar decisiones. |
| opcion_estudio_id | bigint | FK | MAE_OPCION_ESTUDIO.id | Opcional; ausencia no implica incumplimiento. Nulo: requisito común. Con valor: solo se aplica a esa opción. |
| activo | boolean |  | - | Obligatorio. Las nuevas evaluaciones usan solo requisitos activos. |
| tipo_requisito_id | bigint | FK | CAT_TIPO_REQUISITO.id | Obligatorio.  |
| modo_comprobacion | varchar(30) |  | - | Obligatorio. dato_declarado / entidad_oferente |
| documento_exigido | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| detalle_acreditacion | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| referencia_bases | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| fecha_referencia | date |  | - | Opcional; ausencia no implica incumplimiento. Para edad o vigencia cuando aplique |
| destino_id | bigint | FK | CAT_PAIS.id | Opcional. País de la opción al que se limita la condición; requiere opcion_estudio_id. |
| relacion_formacion | varchar(20) | | - | Obligatorio, inicial pendiente. pendiente / independiente / misma_formacion. |
| grupo_formacion | varchar(64) | | - | Clave local a convocatoria obligatoria solo en misma_formacion. Miembros de igual obligatoriedad. |
| equivalencias | jsonb | | - | Obligatorio, inicial []. Tipo, origen, admitido, referencia y contexto país/provincia; contrato cerrado en Ampliacion_comparacion_v06.md. |
## CFG_MOTOR_RECOMENDACION
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| version | varchar(60) |  / único | - | Obligatorio. Identificador de configuración. |
| modelo | varchar(180) |  | - | Obligatorio. Identificador del modelo NLP. |
| revision_modelo | varchar(120) |  | - | Obligatorio. Revisión concreta para reproducibilidad. |
| peso_semantico | numeric(5,4) |  | - | Obligatorio. Peso del componente semántico. |
| peso_reglas | numeric(5,4) |  | - | Obligatorio. Peso del componente de reglas. |
| umbral_alerta | numeric(5,2) |  | - | Obligatorio. Afinidad mínima para notificar. |
| politica_version | varchar(60) |  | - | Obligatorio. Versión de reglas y normalización. |
| creado_por | bigint | FK | MAE_USUARIO.id | Obligatorio. Administrador que registra la configuración. |
| creado_en | timestamptz |  | - | Obligatorio. Fecha de alta. |
## TEC_EMBEDDING_CONVOCATORIA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Texto vectorizado. |
| version_convocatoria | integer |  | - | Obligatorio. Versión del texto. |
| modelo | varchar(180) |  | - | Obligatorio. Modelo utilizado. |
| revision_modelo | varchar(120) |  | - | Obligatorio. Revisión del modelo. |
| hash_texto | char(64) |  | - | Obligatorio. Hash del texto normalizado. |
| vector | real[] |  | - | Obligatorio. Dimensión validada en el backend. |
## TRA_RECOMENDACION
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio. Perfil evaluado. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Oferta evaluada. |
| config_id | bigint | FK | CFG_MOTOR_RECOMENDACION.id | Obligatorio. Configuración exacta. |
| version_perfil | integer |  | - | Obligatorio. Versión del perfil y relaciones. |
| version_convocatoria | integer |  | - | Obligatorio. Versión de la oferta y requisitos. |
| similitud | numeric(7,6) |  | - | Obligatorio. Coseno entre -1 y 1. |
| afinidad | numeric(5,2) |  | - | Obligatorio. Puntuación orientativa 0–100. |
| elegibilidad | varchar(20) |  | - | Obligatorio. Estado orientativo: compatible_declarado / incumplido_declarado / pendiente. Nunca elegibilidad oficial. |
| resumen_evidencia | jsonb |  | - | Obligatorio. Instantánea de criterios, opción y destinos utilizados. El contrato completo de historial sigue pendiente; no garantiza reproducción íntegra por sí sola. |
| calculado_en | timestamptz |  | - | Obligatorio. Momento de evaluación. |
| opcion_estudio_id | bigint | FK | MAE_OPCION_ESTUDIO.id | Obligatorio. Combinación concreta evaluada. |
## TRA_EVALUACION_REQUISITO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| recomendacion_id | bigint | FK | TRA_RECOMENDACION.id | Obligatorio. Evaluación general. |
| requisito_id | bigint | FK | MAE_REQUISITO.id | Obligatorio. Regla comparada. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Garantiza que ambas pertenecen a la misma oferta. |
| resultado | varchar(20) |  | - | Obligatorio. cumple, no_cumple o desconocido. |
| explicacion | text |  | - | Obligatorio. Motivo y evidencia resumida al momento de calcular. |
| dato_comparado | jsonb |  | - | Opcional; ausencia no implica incumplimiento.  |
| tipo_comprobacion | varchar(30) |  | - | Obligatorio. declaracion / externa; no documentos del usuario |
## REL_FAVORITO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| usuario_id | bigint | FK | MAE_USUARIO.id | Obligatorio. Propietario. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio. Convocatoria guardada. |
| creado_en | timestamptz |  | - | Obligatorio. Fecha de guardado. |
## TRA_NOTIFICACION
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| usuario_id | bigint | FK | MAE_USUARIO.id | Obligatorio. Destinatario autorizado. |
| recomendacion_id | bigint | FK | TRA_RECOMENDACION.id | Opcional; ausencia no implica incumplimiento. Resultado relacionado si existe. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Opcional; ausencia no implica incumplimiento. Oferta relacionada. |
| tipo | varchar(30) |  | - | Obligatorio. nueva_coincidencia, cierre o sistema. |
| titulo | varchar(200) |  | - | Obligatorio. Texto visible. |
| mensaje | text |  | - | Obligatorio. Descripción. |
| clave_evento | varchar(180) |  | - | Obligatorio. Idempotencia dentro del destinatario. |
| creado_en | timestamptz |  | - | Obligatorio. Fecha de emisión. |
| leida_en | timestamptz |  | - | Opcional; ausencia no implica incumplimiento. Nulo hasta marcar como leída. |
## AUD_EVENTO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio. Identificador interno. |
| actor_id | bigint | FK | MAE_USUARIO.id | Obligatorio. Administrador responsable. |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Opcional; ausencia no implica incumplimiento. Convocatoria afectada. |
| fuente_id | bigint | FK | CFG_FUENTE.id | Opcional; ausencia no implica incumplimiento. Fuente afectada. |
| config_id | bigint | FK | CFG_MOTOR_RECOMENDACION.id | Opcional; ausencia no implica incumplimiento. Configuración afectada. |
| accion | varchar(60) |  | - | Obligatorio. Tipo de cambio. |
| cambios | jsonb |  | - | Obligatorio. Campos permitidos antes/después; sin credenciales. |
| creado_en | timestamptz |  | - | Obligatorio. Momento de la acción. |
## MAE_EXPERIENCIA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio.  |
| perfil_id | bigint | FK | MAE_PERFIL.id | Obligatorio.  |
| area_id | bigint | FK | CAT_AREA.id | Opcional; ausencia no implica incumplimiento.  |
| cargo | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| descripcion | text |  | - | Opcional; ausencia no implica incumplimiento.  |
| fecha_inicio | date |  | - | Obligatorio.  |
| fecha_fin | date |  | - | Opcional; ausencia no implica incumplimiento. NULL si continúa |
| actual | boolean |  | - | Obligatorio.  |
## CAT_TIPO_BECA
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio.  |
| nombre | varchar(100) |  / único | - | Obligatorio.  |
| descripcion | text |  | - | Opcional; ausencia no implica incumplimiento.  |
## MAE_BENEFICIO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio.  |
| convocatoria_id | bigint | FK | MAE_CONVOCATORIA.id | Obligatorio.  |
| opcion_estudio_id | bigint | FK | MAE_OPCION_ESTUDIO.id | Opcional; ausencia no implica incumplimiento.  |
| concepto | varchar(100) |  | - | Obligatorio. matrícula, aranceles, manutención, etc. |
| porcentaje | numeric(5,2) |  | - | Opcional; ausencia no implica incumplimiento. 0 a 100; referido al concepto |
| monto | numeric(12,2) |  | - | Opcional; ausencia no implica incumplimiento.  |
| moneda | char(3) |  | - | Opcional; ausencia no implica incumplimiento.  |
| periodicidad | varchar(30) |  | - | Opcional; ausencia no implica incumplimiento. único/mensual/anual/otra |
| detalle | text |  | - | Opcional; ausencia no implica incumplimiento.  |
## CAT_TIPO_REQUISITO
| Atributo | Tipo lógico | Clave | Referencia | Regla / significado |
|---|---|---|---|---|
| id | bigint | PK | - | Obligatorio.  |
| codigo | varchar(40) |  / único | - | Obligatorio.  |
| nombre | varchar(100) |  | - | Obligatorio.  |
| esquema_valor | jsonb |  | - | Obligatorio. Contrato por tipo para valor_estructurado; no texto libre sin validar |
