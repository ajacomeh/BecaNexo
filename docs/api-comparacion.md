# Comparación explicable por opción

## API

`GET /api/becas/<id>/comparacion/` requiere sesión activa de postulante. No acepta parámetros, cuerpo ni identificador de usuario/perfil. El propietario procede de `request.user`. Devuelve 200 incluso si el perfil no existe: las condiciones sin información quedan desconocidas. Administradores y anónimos reciben 403; borradores, pausadas e IDs inexistentes, 404; parámetros/cuerpo no admitidos, 400; métodos de escritura no soportados, 405 tras comprobar autenticación/CSRF. Se hereda `AuthView` con sesiones, CSRF y `never_cache`. GET no escribe datos.

La respuesta contiene `convocatoria_id`, `calculado_en`, `aviso`, `criterio_destacada`, `opcion_destacada_id` y `opciones`. Cada opción activa incluye `resultados_destino`: país/código, nombre, resultado, resumen y requisitos aplicables. Se combinan exclusivamente comunes + opción + país. El campo de compatibilidad `opciones[].requisitos` contiene una sola alternativa con el estado agregado, nunca mezcla datos entre destinos; el frontend usa el desglose completo. Sin países definidos se devuelve una alternativa pendiente con país null, sin inventar destinos.

Cada requisito contiene `id`, `tipo`, `descripcion`, `obligatorio`, `ambito`, `resultado` (cumple/no_cumple/desconocido), `explicacion`, `dato_declarado`, `condicion_exigida` (valores, fecha de referencia y condiciones documentales), `comprobacion_externa`, `estado_documental` y `seccion_perfil`. Este último indica `datos-personales`, `formacion-academica`, `idiomas`, `experiencia` o `disponibilidad` solo cuando falta o no coincide un dato que el postulante puede actualizar; vale null ante dudas de las bases, equivalencias o verificación documental. No devuelve perfil completo, correo, fecha de nacimiento ni credenciales; en edad solo devuelve años a la fecha publicada. Una coincidencia académica devuelve únicamente los campos de una formación utilizados, sin institución ni historial de todas las formaciones.

El diccionario/JSON de TRA_EVALUACION_REQUISITO y la instrucción de esta etapa usan los tres estados anteriores. El documento de reglas v05 menciona además cumple_declarado/no_cumple_declarado/pendiente_datos/verificacion_externa: la API representa ese matiz mediante explicación, ámbito y los campos externos, sin modificar el modelo ni persistir resultados.

## Reglas soportadas y límites

| Tipo | Comparación actual |
| --- | --- |
| NACIONALIDAD | Pertenencia a los países admitidos; contrato vigente limitado a EC. |
| EDAD | Años cumplidos en `fecha_referencia`; límites mínimo/máximo inclusivos. Sin esa fecha no se usa hoy. |
| IDIOMA | Mismo idioma; orden MCER A1, A2, B1, B2, C1, C2. Ausencia de idioma/nivel es desconocida. |
| FORMACION | Nivel dentro de `niveles_admitidos`, estado exacto y título obtenido si se exige. Sin lista explícita, pendiente; se conserva `nivel_minimo` antiguo como texto estructurado de origen, no como jerarquía. `titulo_obtenido=false` no exige ausencia de título. |
| TITULO_AREA | Título normalizado o equivalencia administrativa con procedencia y área de catálogo, en una misma formación. Nombre diferente sin equivalencia es desconocido; área conocida fuera de las admitidas no coincide. |
| PROMEDIO | Mínimo inclusivo con Decimal y extremos de escala idénticos. Escalas distintas o promedio ausente quedan pendientes. No interpreta texto de equivalencia como fórmula. |
| DEDICACION | Disponibilidad completa satisface requisitos de completa o parcial; parcial solo satisface parcial; ambas satisface completa, parcial y el valor legado ambas. Un requisito antiguo que admite únicamente ambas no se reinterpreta: solo ambas lo satisface. Sin declarar queda desconocido. Sin requisito de dedicación no se genera un incumplimiento artificial. |
| TRASLADO | Solo se exige por regla explícita. Se evalúa en cada destino; extranjero requiere disponibilidad al extranjero. Virtual no implica traslado. Un destino antiguo dentro del JSON que no coincide con la alternativa deja esa condición pendiente de aclarar ámbito; no se convierte automáticamente en FK. |
| RESIDENCIA | País por catálogo; provincia y ciudad requieren contexto inequívoco o equivalencia con país/provincia y referencia. Múltiples países/provincias no implican combinaciones territoriales equivalentes. |
| EXPERIENCIA | Filtra área, une intervalos superpuestos y recorta a `fecha_referencia` publicada. Devuelve los periodos utilizados, pero meses siguen desconocidos sin una convención ejecutable concreta aprobada; no interpreta texto ni convierte jornadas. |
| ACREDITACION, DOCUMENTO, OTRO | Desconocido con verificación por entidad oferente. No se solicitan archivos. |

### Nivel deducido por reglas y sugerencia de IA local (v1.1, 28/11/2026)

- **Nivel deducido (sin IA, en memoria, sin persistir ni modificar requisitos).** Solo puede producir «cumple» ante una coincidencia exacta; en cualquier otro caso se mantiene «desconocido». Nunca produce «no_cumple» ni infiere jerarquías: por ejemplo, una maestría no cuenta como «tercer nivel». La explicación indica que el nivel se dedujo del texto de la convocatoria.
  - `FORMACION` sin `niveles_admitidos`: se deduce si el texto publicado nombra únicamente la familia de su `nivel_minimo` (bachillerato o grado), como en «Ser Bachiller».
  - `TITULO_AREA` que solo pide un nivel de título: un único título admitido, sin áreas, y tanto el título como el texto publicado nombran la misma y única familia (bachillerato, tercer nivel/grado, maestría o doctorado).
    - No se deduce si hay cualquier condición adicional: fechas, «hasta», «o equivalente», «o ser profesor…», «que le habilite el acceso…», el programa al que aplica, «oficial»…
    - Tampoco con «cuarto nivel» o «posgrado», que no distinguen el nivel.
    - Basta una formación declarada de ese nivel exacto, concluida y con título obtenido.
- **Sugerencia de IA local (`sugerencia`).** Solo en `GET /api/becas/<id>/comparacion/` (no en «Para ti» ni en los avisos).
  - Se aplica a requisitos `TITULO_AREA` revisados que quedaron «desconocido».
  - El modelo local compara el título o área exigidos con cada formación declarada. Sobre el umbral 0,70 se añade `sugerencia` (`etiqueta` «Posible coincidencia (sugerida por IA local)», `formacion`, `explicacion`).
  - **Nunca cambia `resultado` ni la elegibilidad**. Sin modelo no hay sugerencia ni error.
  - El umbral se calibró el 27/11/2026: las carreras distintas llegaron como máximo a 0,48, los requisitos que solo piden un nivel a 0,66 y las carreras equivalentes van de 0,51 a 0,83. Es conservador: puede omitir equivalencias reales (por ejemplo, «Sistemas» y «Software»).
  - Con los datos de esa fecha no aparece ninguna sugerencia, porque los 18 `TITULO_AREA` públicos piden un nivel, no una carrera.

Solo se ejecutan reglas revisadas cuyo esquema versionado, operador, campos y modo coinciden con el contrato. Reglas inválidas o desconocidas quedan pendientes sin provocar cumplimiento automático.

Para formación/título/promedio, el administrador configura `relacion_formacion`: pendiente, independiente o misma_formacion. El último exige `grupo_formacion`, clave local a convocatoria, con igual obligatoriedad de miembros. Una formación debe satisfacer todos los miembros aplicables al destino. Si ninguna coincide pero existe candidata viable con datos desconocidos, queda pendiente; si todas se descartan por datos conocidos, incumple el grupo. Cada miembro devuelve el resultado y explicación conjunta; al coincidir, los datos utilizados son de la misma formación. En incumplimiento grupal no se expone un historial de todas las formaciones. Un grupo no invalida condiciones opcionales como si fueran obligatorias. Las relaciones antiguas pendientes no se convierten automáticamente a independientes.

## Resultado y presentación

Si una referencia de experiencia es futura y hay registros en curso, la condición queda pendiente sin proyectar experiencia como ya realizada. No se inventa fecha de fin ni se sustituye la referencia de las bases por otra fecha de cálculo.

La relación académica indefinida convierte las coincidencias individuales en pendientes de relación. Un incumplimiento individual comprobable se conserva y determina el resumen; no se oculta tras la ambigüedad.

1. Algún requisito obligatorio no coincide: «No coincide con un requisito obligatorio».
2. Sin incumplimiento obligatorio, pero con información obligatoria comprobable desconocida, o sin condiciones obligatorias comprobables: «Pendiente de comprobar».
3. Todos los obligatorios comprobables coinciden: «Coincide según tus datos declarados». Las verificaciones externas siguen visibles y pendientes, incluso si esta frase aparece.

Las condiciones opcionales se muestran pero no determinan el resumen. Un documento exigido anexo a una regla declarada conserva estado documental pendiente aunque coincida el dato. `estado_documental=no_evaluado` no significa que la entidad no exija documentos.

Estas reglas se aplican por destino. Agregado de opción: si un destino coincide, coincide; en caso contrario, si alguno queda pendiente, pendiente; solo si todos incumplen, incompatible. Los requisitos específicos de otro país no se aplican. Preferencias no participan. La interfaz muestra cada resultado territorial en un desplegable con el estado siempre visible.

Sin requisitos identificados se muestra información ausente, nunca cumplimiento ni «no se exige». Una convocatoria aparece una vez; opciones incompatibles se presentan aparte y siguen consultables. Se destaca una opción coincidente o, en su ausencia, pendiente, explicando ese estado con lenguaje comprensible. Si todas incumplen no se destaca ninguna. Es presentación determinista, no ranking ni afinidad.

## Configuración administrativa e integridad v2

Se reutilizan POST/PATCH `/api/gestion/convocatorias/:id/requisitos/[:requisito/]` y las rutas existentes de publicación: solo administrador, sesiones/CSRF y auditoría. Nuevos campos: `destino` (ID de CAT_PAIS, requiere opción y país incluido), `relacion_formacion`, `grupo_formacion`, `equivalencias`. Se rechaza un grupo no académico, incoherencia de obligatoriedad y retiro de países aún referenciados. Editar retira la publicación hasta revisión, como antes.

Cada equivalencia es `{tipo, origen, admitido, referencia, pais, provincia}`. Tipo titulo/provincia/ciudad; textos obligatorios con referencia a las bases. País/provincia nulos para títulos; país admitido para provincias; país y provincia admitida para ciudades. No hay equivalencias globales o encadenadas ni orígenes duplicados en el mismo contexto. El formulario permite añadir/quitar filas, seleccionar niveles/destinos y asignar grupos sin escribir JSON. El servidor aplica las mismas reglas y revalida al publicar.

## Interfaz, vigencia y reproducción

En `/becas/:id`, el postulante pulsa «Comparar requisitos». Un visitante tiene enlace al login con retorno seguro al mismo detalle; al volver debe pulsar para comparar. El administrador no tiene controles de comparación.

La consulta muestra carga, error/reintento y resultados por opción con coincidencias, incumplimientos y pendientes separados. Antes del detalle aparece un resumen de la opción destacada o primera opción, y de su destino pertinente cuando corresponde. Cuenta todos los requisitos de esa alternativa en tres estados y muestra los nombres de sus tipos, agrupando repeticiones; el estado general considera solo los obligatorios. El resumen superior no se repite en el detalle de la misma alternativa; los demás destinos conservan su propio resumen. No es un porcentaje ni una probabilidad de adjudicación. Los requisitos con `seccion_perfil` ofrecen un enlace a la sección editable, con foco en su encabezado. Dos botones superiores llevan a pantallas distintas: «Actualizar perfil» abre `/perfil` (con ancla a datos personales, formación o experiencia cuando procede) y «Actualizar preferencias» abre `/preferencias#preferencias`. Los enlaces de requisitos de idioma y disponibilidad llevan a sus apartados de `/preferencias`. Las preferencias no determinan elegibilidad. «Actualizar comparación» vuelve a calcular. Al volver a la ventana se renueva una comparación ya abierta; navegar fuera y regresar también elimina el resultado previo. En un fallo de actualización se retiran los resultados anteriores. No hay caché de evaluaciones, persistencia, IA ni sincronización continua en una pestaña que permanece en primer plano.

Revisadas las tablas TRA_RECOMENDACION y TRA_EVALUACION_REQUISITO: exigen configuración del motor, similitud, afinidad y FK de recomendación. Se mantienen sin crear ni rellenar ceros. La migración aditiva convocatorias.0002 amplía MAE_REQUISITO; detalles y diferencias con el ER en modelo/Ampliacion_comparacion_v06.md.

Pruebas backend: `.\.venv\Scripts\python.exe backend/manage.py test usuarios perfiles convocatorias favoritos --keepdb --verbosity 2`, sin paralelismo, exclusivamente test_becanexo_db. Frontend, con Node 24 en PATH desde frontend: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build`.

Recorridos reales: `npm.cmd run test:e2e -- --config playwright.comparison.config.js`. Ejecuta comparison.spec.js y rules.spec.js; reutiliza servidores disponibles. El primero conserva la demostración inicial y renombra de forma idempotente únicamente «DEMOSTRACIÓN C · Edad pendiente» a «DEMOSTRACIÓN C · Edad máxima», con auditoría y sin tocar fechas. El segundo usa una oferta y perfil sintéticos separados (DEMO reglas v2), configura desde formularios niveles admitidos, título equivalente con referencia, promedio en el mismo grupo y traslado obligatorio solo para España. Publica como administrador y compara como postulante: Ecuador coincide, España incumple, documentos pendientes. Las sesiones de fixture se capturan en memoria, no se registran ni cambian last_login, y se cierran al terminar. No modifica perfiles personales ni el superusuario. Resultados en avance.md.

Para incorporar afinidad posteriormente faltan modelo semántico local y evaluación de ejemplos, texto/embeddings, configuración versionada, decisiones de componentes faltantes y diseño de persistencia con instantáneas. Los pesos aprobados no se calculan en esta etapa. Rastreo y notificaciones siguen fuera del alcance implementado.
