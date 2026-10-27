# Avance de BecaNexo

## Edición del nombre visible propio (26 de octubre de 2026)

- Revisados AGENTS, Git, usuario, autenticación, contexto y navegación. Conservado el estado previo; no se editaron cuentas de desarrollo ni datos de los cinco escenarios de reunión.
- `PATCH /api/auth/me/` acepta exclusivamente nombre de texto, recorta extremos, exige contenido y máximo 180 según el modelo. Rechaza otros campos y query params. Propietario exclusivamente request.user, disponible para ambos roles activos; sesiones, CSRF y never_cache heredados. Guarda solo nombre mediante update_fields y devuelve únicamente nombre. Sin migraciones ni cambios en correo, contraseñas, privilegios o perfil académico.
- Acción discreta en cuenta de barra lateral; diálogo nativo con campo precargado y aclaración de independencia del perfil, guardar/cancelar/Escape, foco restaurado, carga y bloqueo de doble envío. Errores conservan contexto/entrada y permiten reintentar; éxito actualiza contexto compartido sin recarga ni cierre de sesión. Se presenta texto, no HTML.
- Backend: Django check correcto y makemigrations --check --dry-run sin cambios. Suite usuarios: 34 pruebas aprobadas (71,611 s); añadido después recorrido real login/PATCH/logout/nueva sesión y reejecutadas las 5 pruebas específicas, todas aprobadas (9,685 s). Exclusivamente test_becanexo_db con --keepdb sin paralelismo, cuentas dedicadas del test y CSRF habilitado. Ese recorrido usa backend, sesiones y PostgreSQL reales mediante APIClient, no navegador. No se generó una cuenta nueva en desarrollo ni se tocó el superusuario.
- Frontend: 90 pruebas aprobadas en 10 archivos (72,40 s), incluyendo ambos roles, cancelación, errores, doble envío, actualización de contexto y presentación de caracteres HTML como texto. El arnés inicial necesitó suplir showModal/close ausentes en jsdom y usar la aserción toHaveFocus de jest-dom; no se relajaron las verificaciones. Build correcto (2,52 s). Lint sufrió un fallo de memoria y se repitió aisladamente fuera del sandbox: salida 0, sin errores.
- Edge inicial: diálogo a 320 px aprobado con API simulada (guardar, Escape, foco y recarga). Administración, poca altura y catálogo también aprobaron; dos recorridos antiguos agotaron timeout durante carga/navegación bajo presión de memoria. Reejecución aislada final: 6 pruebas aprobadas (39,3 s), sin cambiar aserciones ni límites de tiempo; escritorio 1440/1366 y móvil 390/320, cierre de sesión accesible y menú desplazable conservados. No se declara navegador con sesiones reales: queda pendiente ese recorrido integrado manual, mientras que el backend real sí se probó en PostgreSQL de pruebas. Contrato y pasos manuales en docs/api-autenticacion.md. Sin dependencias, commit ni publicación.

## Demostración de revisión de avances (26 de octubre de 2026)

- Recuperada la instrucción original tras la interrupción. No existían comando ni registros de esta demostración; se conservaron todos los cambios sin commit del catálogo. Revisados AGENTS, modelos/serializers, contratos y documentación v0.6. Bases comprobadas: desarrollo becanexo_db y pruebas test_becanexo_db; migraciones existentes aplicadas, sin nuevas migraciones.
- Añadidos `backend/convocatorias/demo_avances.py`, comando `cargar_demo_avances` y `test_demo_avances.py`. Vista previa por defecto y `--vista-previa` sin escrituras, `--aplicar --actor-id` con transacción/lock de PostgreSQL, validadores y servicio de publicación existentes. Rechaza colisiones/cargas parciales/cambios sin sobrescribir. AUD_EVENTO conserva origen manual, actor y objeto válidos; una huella del fixture permite reutilizarlo excluyendo contraseñas, last_login, sesiones y favoritos. No crea rastreos ni altera el comparador.
- 10 pruebas específicas aprobadas (10,607 s): escenarios A–E, ausencia de promedio/escala en Educación, grupo TIC sin mezclar Administración, documentación externa pendiente, vista previa sin INSERT/UPDATE/DELETE, idempotencia incluso después de cambiar contraseña y last_login, colisiones, diferencias, rollback y conservación de un conjunto anterior completo. API pública y comparación autenticada comprobadas mediante APIClient. Regresiones completas: 121 pruebas aprobadas (78,217 s), cero fallidas/omitidas, test_becanexo_db con --keepdb sin paralelismo. Django check correcto; makemigrations --check --dry-run: sin cambios.
- Después de superar pruebas, ejecutado en becanexo_db `cargar_demo_avances --aplicar --actor-id 8`: creado oferente ficticio ecuatoriano, cuenta revision-avances@example.com (ID 13) sin contraseña utilizable, perfil con TIC 7/10, Administración 9/10 y Educación con promedio y escala nulos; inglés B2, residencia y disponibilidad declaradas. Creadas cinco convocatorias IDs 4–8, siete opciones, doce beneficios, cuarenta y cinco requisitos y doce eventos de auditoría. Relaciones de perfil: tres áreas, dos destinos y una preferencia. Reutilizados catálogos y actor administrador previo ID 8, sin modificación. Fechas fijas: apertura 20/10/2026, cierre 30/11/2026, inicio académico 01/03/2027; ofertas abiertas en la fecha de revisión.
- Repetida la carga en desarrollo: `reutilizada`, sin duplicados ni nuevas publicaciones. Motor real: A cumple con documentos pendientes; B no_cumple por B2 frente a C1; C desconocido en grupo Educación/promedio; D cumple/no_cumple/desconocido por opción; E no_cumple porque ninguna formación satisface conjuntamente TIC y promedio 8/10. La tercera formación de Educación no hace que E quede pendiente porque se descarta por área conocida.
- APIClient de desarrollo: catálogo devuelve 200 y cinco nuevas ofertas; cinco detalles y cinco comparaciones devuelven 200. Comparaciones con force_authenticate en memoria, no con sesión real de navegador. Huellas antes/después de filas previas en 22 tablas coinciden (no incluyen password/last_login); todos los registros anteriores comparados conservados. No hubo migrate, limpieza, restauración, cambio de credenciales previas ni permisos. El frontend pendiente no se editó ni se repitieron sus pruebas en esta tarea.
- Guía completa en `docs/guia-demostracion-avances.md`, con enlaces locales, arranque, datos, límites, arquitectura, recorrido y contraseña mediante `changepassword revision-avances@example.com` (entrada oculta y validadores de Django). Pendiente para el presentador: establecer su contraseña y recorrer en navegador con login real. No se generó ni documentó contraseña. El área por opción se describe en programa y requisitos; el modelo solo tiene relación de áreas a nivel convocatoria. Sin IA, rastreo, notificaciones, nuevas reglas, commit ni publicación.

## Catálogo público compacto (26 de octubre de 2026)

- Base confirmada: commit 5480e63 y árbol limpio al inicio. Conservados los ajustes de barra lateral, cabeceras y paginación. Presentación pública separada en PublicCatalog, CatalogFilters y CatalogCard, con estilos limitados a `.public-catalog`; gestión administrativa y detalle conservados.
- Cuatro filtros iniciales, secundarios en «Más filtros» con contador de aplicados, valores vacíos «Todos…», aplicar/limpiar sincronizados con URL y vuelta a página uno. Ordenación inmediata junto al recuento, predeterminada `recientes` según el servidor. Paginación solo cuando count supera page_size.
- Tarjetas sin ausencias redundantes: beneficios comunes frente a específicos, porcentajes por concepto sin sumas, opciones/niveles/modalidades/destinos deduplicados, fecha breve con la zona horaria existente y acciones al pie. «Ver detalle» principal y favoritos secundarios. Sin fecha ni texto original: una sola leyenda «Fecha de cierre no informada». Se conserva texto original de cierre atribuido a la fuente; no se inventa permanencia.
- Revisión del contrato: el listado ya incluye opciones activas, países por ID y ámbito de beneficios. No se amplió el backend ni se pidieron detalles por cada tarjeta. Documentación funcional en `docs/catalogo-publico.md`.
- Pruebas frontend: 85 aprobadas en 9 archivos con `npm.cmd test -- --maxWorkers=1` (34,58 s), incluidos 10 casos nuevos de filtros, limpieza, orden, paginación, opcionales, beneficios, destinos, fechas, error/reintento; regresiones de favoritos y retorno seguro incluidas. Intentos iniciales concurrentes sufrieron errores de memoria y un timeout; no se cuentan como aprobados. Reejecución secuencial correcta. Lint y build aprobados.
- Edge: 5 pruebas aprobadas (18,8 s) con playwright.layout.config.js, roles y API simulados sin datos de desarrollo escritos. Revisados 1440×900, 1366×768, 390 y 320 px, desplazamiento real y barra lateral/cierre accesible, filtros secundarios, orden, limpieza, favoritos anónimos y paginación. El recorrido detectó una etiqueta ambigua del selector Estado; corregida con label/for explícitos. Capturas revisadas; se corrigió además el estilo de favorito anónimo para mantenerlo secundario respecto a «Ver detalle». Capturas ignoradas en frontend/test-results.
- Pendientes de verificación manual: zoom nativo al 200 % y sesiones reales. Solo se comprobó reflujo equivalente a 720×450 y datos interceptados. Pruebas E2E antiguas de API real ajustadas al nombre «Ver detalle», pero no ejecutadas porque crean sesiones o modifican fixtures; no se presentan como aprobadas en esta tarea. No se modificaron backend, datos, fechas, credenciales, dependencias ni migraciones. Sin commit ni publicación.
- Cierre del bloque: repetidas las 85 pruebas con un trabajador tras ajustar las etiquetas accesibles (38,68 s), todas aprobadas; lint y build finales correctos. Repetido el recorrido específico de catálogo tras corregir la jerarquía del favorito anónimo: 1 aprobado (3,8 s), capturas de tarjetas en escritorio/390/320 revisadas de nuevo. `git diff --check` sin errores.

## Ajuste visual acotado de layouts (26 de octubre de 2026)

- El árbol de trabajo estaba limpio al iniciar. Cambiados únicamente estilos/componentes frontend, pruebas visuales y este documento; no se tocaron API, permisos, reglas, modelo, datos ni dependencias.
- Barra lateral compartida de postulante y administrador: sticky, top 0, altura 100dvh y align-self start en escritorio. Ancestros sin overflow que interfiera. Menú con desplazamiento propio y bloque de cuenta inferior; ajuste para poca altura y espacio para el foco. En móvil permanece la navegación flexible existente, sin panel fijo superpuesto.
- Grupo heading-actions para cabecera pública y acciones administrativas: elimina margen/ancho de formulario heredado, centra controles y permite envolverlos. Ajustado también el enlace directo del encabezado de favoritos. Oferentes: título y creación antes de la lista, paginación como cierre con etiqueta accesible. Botones de paginación proporcionados en catálogo, administración, favoritos y oferentes, sin modificar filtros ni tamaño de página.
- Verificación con Node 24: `npm.cmd test` aprobó 75 pruebas en 8 archivos; `npm.cmd run lint` y `npm.cmd run build` aprobaron, repetidos después del ajuste final del foco. `git diff --check` sin errores de espacios.
- `npm.cmd run test:e2e -- --config playwright.layout.config.js`: 4 pruebas finales aprobadas (15,8 s) en Edge, un trabajador. API y roles simulados mediante interceptación, sin crear sesiones ni escribir en PostgreSQL. Se verificaron visitante, postulante y administrador, 1440×900, 1366×768, 390×844 y 320×700; capturas del viewport al inicio y tras desplazamiento real hasta abajo, controles de cabecera alineados, ausencia de desbordamiento horizontal, filtros, anterior/siguiente y estados deshabilitados, favoritos, enlaces a login/registro y apertura/cancelación de creación de oferente. Capturas en frontend/test-results (ignoradas por Git), revisadas visualmente, incluidos inicio/final de la barra lateral y menú desplazable a 1366×400.
- Los primeros intentos de las pruebas visuales detectaron errores del arnés: interceptación accidental del módulo src/api/client.js, comparación estricta de cero negativo y escritura antes de completarse el cambio de página. Corregidos sin cambiar comportamiento de la aplicación ni quitar las comprobaciones correspondientes. Un ensayo con CSS zoom no reprodujo correctamente el zoom nativo y no se cuenta como verificación aprobada de zoom.
- Pendiente visual: zoom **nativo** del navegador al 200 % y recorrido con sesiones reales. Se comprobó reflujo a 720×450 (equivalente al viewport CSS de 1440×900 al 200 %) y acceso al cierre de sesión con poco espacio, pero no se presenta como prueba del control de zoom de Edge. Esta revisión no sustituye una auditoría de accesibilidad completa. No se repitió backend porque no cambió. Sin commit ni publicación.

## Estado actual — reglas aprobadas v2 (26 de octubre de 2026)

- Conservados los cambios previos sin commit. Propuesta previa en propuesta-reglas-comparacion-v2.md; desarrollo tenía aplicada solo convocatorias.0001_initial.
- Escritos cuatro campos aditivos en MAE_REQUISITO, migración 0002 revisada (cuatro AddField y dos restricciones, sin transformar valores antiguos), equivalencias con procedencia/contexto, grupos explícitos y evaluación por destino. Formularios administrativos sin JSON manual, permisos/CSRF/auditoría conservados.
- 110 pruebas backend aprobadas en test_becanexo_db con --keepdb, sin paralelismo (65,719 s). La migración 0002 se aplicó únicamente por el ejecutor de pruebas. Django check y makemigrations --check --dry-run correctos. Suite frontend inicial 72 aprobadas; añadidos tres casos de formulario/destino: uno detectó selector de prueba incompatible con asterisco obligatorio, corregido usando el nombre accesible. Reejecución pendiente.
- Cierre de pruebas: 75 frontend aprobadas en 8 archivos (13,88 s), lint y build aprobados. Tras normalizar la clave de grupo vacía a NULL en el servidor, repetidas las 14 pruebas v2 (0,736 s), todas aprobadas; el caso verifica rechazo para misma_formacion y aceptación para independiente sin error 500. Las regresiones completas previas fueron 110 backend, todas aprobadas; cero fallidas u omitidas en ejecuciones finales. Se ajustaron expectativas antiguas exclusivamente por reglas aprobadas: mínimo sin lista = pendiente y ciudad sin contexto suficiente = pendiente.
- Revisión adicional de experiencia: una referencia futura con periodos actuales queda desconocida sin proyectar experiencia aún no realizada. Añadido caso y ejecutadas las 15 pruebas v2 (0,795 s), todas aprobadas; la suite completa de 110 anterior no se repitió para este guard y normalización acotados. La suite total contiene ahora 111 casos, de los que este bloque final reejecutó los 15 específicos.
- Migraciones de desarrollo: se volvió a comprobar 0001 [X] y 0002 [ ]; revisado migrate --plan; aplicada convocatorias.0002_requisito_destino_requisito_equivalencias_and_more a becanexo_db, confirmada [X]. Cargados catálogos con contratos FORMACION/EXPERIENCIA v2 sin reescribir JSON de requisitos. No se borraron ni reconstruyeron tablas. Django check y makemigrations --check --dry-run finales correctos.
- Recorrido Edge: 2 pruebas aprobadas (18,7 s) con playwright.comparison.config.js, un trabajador, API y sesiones reales de fixture. El administrador configuró desde formularios niveles admitidos, equivalencia con procedencia, grupo título/promedio/nivel y condición de traslado para España; publicó y el postulante vio Ecuador coincidente y España incompatible sin descartar la opción. Auditoría comprobada. Capturas de escritorio 1440×1000 y móvil 390×844 revisadas, sin desbordamiento horizontal ni superposiciones; estados por destino y documentos pendientes visibles. No es auditoría de todos los navegadores ni de accesibilidad completa.
- Renombrada solo la opción identificada de convocatoria DEMO ID 2: DEMOSTRACIÓN C · Edad pendiente → DEMOSTRACIÓN C · Edad máxima, con auditoría. Fixture idempotente actualizada. Hash de convocatorias originales IDs 1 y 2, opciones, requisitos (campos anteriores) y beneficios, normalizando exclusivamente ese nombre, coincide antes/después: fechas y contenido anterior conservados.
- Nueva demostración separada: convocatoria ID 3 «DEMOSTRACIÓN · Reglas aprobadas v2», una opción virtual EC/ES, cinco requisitos (tres académicos agrupados, traslado de España y documento externo), una cuenta postulante DEMO con contraseña inutilizable, perfil y formación sintéticos. Reutilizado oferente ficticio y administrador DEMO sin cambiar sus datos. Sesiones cerradas al terminar; sin tocar perfiles personales ni superusuario. No se insertaron conversiones ficticias, fechas nuevas en ofertas anteriores o resultados de IA.
- Documentación actualizada: propuesta previa, decisiones aprobadas, API, Diccionario, Reglas_y_requisitos y modelo completo Modelo_logico_v06.json con suplemento respecto al ER v05 histórico. No quedan comprobaciones de este bloque pendientes. Límites explícitos: conversión entre escalas y cálculo numérico de meses requieren fórmula/convención concreta aprobada; periodos se filtran, recortan y unen, pero no se traducen a meses. Requisitos sin evidencia suficiente quedan desconocidos. No se implementaron IA, rastreo ni notificaciones; sin commit ni publicación.

## Estado actual — comparación explicable (25 de octubre de 2026)

- Leídos AGENTS, modelo lógico/diccionario/reglas v05, contratos implementados, perfiles y referencia visual del detalle (página 12). Árbol inicial limpio en 0ec7218; se conserva la bienvenida y consulta pública.
- Documentadas decisiones aprobadas en decisiones-recomendacion-rastreo.md. Escritos servicio sin persistencia, GET propio del postulante y comparación por opción en detalle. Contrato y ambigüedades en api-comparacion.md. No hay IA, rastreo ni porcentajes.
- Primera verificación: Django check correcto; makemigrations --check --dry-run sin cambios; 95 pruebas backend aprobadas en test_becanexo_db con --keepdb, sin paralelismo (41,191 s). 72 pruebas frontend aprobadas (14,17 s); lint y build aprobados. Cero fallidas u omitidas.
- Revisión final: una relación académica indefinida no oculta un incumplimiento individual comprobable. Añadido caso explícito y repetidas regresiones: 96 pruebas backend aprobadas en test_becanexo_db (40,882 s), 72 frontend aprobadas (13,49 s); lint y build aprobados. Cero fallidas u omitidas. Sin diferencias de modelo ni migraciones; no se ejecutó migrate en desarrollo.
- Recorrido real Edge: 1 aprobado (8,7 s), API real y sesión de fixture, tres opciones con resultados cumple/no_cumple/desconocido, verificaciones externas pendientes, recarga y actualización. No se usó login por contraseña ni se alteró last_login. Capturas de la comparación en escritorio 1440×1000 y móvil 390×844 revisadas; sin desbordamiento horizontal, texto superpuesto ni condiciones documentales ocultas. No sustituye una auditoría de accesibilidad o de otros navegadores.
- El primer intento de navegador se detuvo porque el puerto 8000 estaba ocupado, antes de crear fixtures. playwright.comparison.config.js reutiliza los servidores locales y limita el recorrido a comparación; servidores del usuario conservados.
- Datos de desarrollo creados exclusivamente para DEMOSTRACIÓN: una cuenta postulante con contraseña inutilizable, un perfil EC y una declaración inglés B2, una institución ficticia, convocatoria ID 2, tres opciones/destinos, cinco requisitos, un beneficio y un evento de auditoría con el administrador DEMO existente. Comprobados los conteos por la clave exclusiva de fixture. No se modificaron perfiles personales, credenciales ni superusuario. La sesión de fixture se cerró al terminar; los datos sintéticos permanecen identificados y la preparación es idempotente sin sobrescribir fixtures existentes.
- Documentación terminada: decisiones-recomendacion-rastreo.md y api-comparacion.md. Pendientes de negocio: orden académico, equivalencias de títulos/territorios, conversiones de escalas, cálculo de meses y vínculo de requisitos académicos a una misma formación. Estos casos conservan desconocido; no bloquean los tipos definidos. Afinidad futura requiere motor local, configuración, ejemplos revisados y diseño de persistencia, sin ceros ficticios. No se implementaron IA, rastreo ni notificaciones. Sin commit ni publicación.

## Estado actual — bienvenida pública (25 de octubre de 2026)

- Reanudación: comprobados AGENTS, git status/diff y Welcome.jsx sin versionar. Base 001af22; conservados los cambios parciales de App/AuthLayout/Welcome y toda la consulta pública. Referencia visual de presentación revisada en el PDF v05, página 2.
- Terminada `/` con contenido propio, encabezado, presentación, ilustración SVG local, beneficios actuales, pasos, cierre y aclaración externa. Todas las clases welcome tienen estilos; identidad Inter/azul marino/azul/verde azulado, diseño adaptable, enlaces nativos y foco visible. Login y registro enlazan a `/`; usuarios con sesión ven Mi panel. No se cambian permisos, CSRF ni retorno seguro.
- Verificación real: 65 pruebas frontend aprobadas en 6 archivos (12,64 s), cero fallidas u omitidas en la ejecución final. Incluyen los 59 casos existentes y 6 nuevos. Primer intento: 4 fallos en pruebas nuevas por devolver el mock como limpieza de beforeEach y pulsar el enlace antes de terminar la restauración de sesión; corregida la preparación y la espera, manteniendo las aserciones. Lint y build aprobados; Django check sin incidencias; git diff --check sin errores de espacios.
- Navegador Edge: 3 recorridos aprobados con playwright.public.config.js, un trabajador. Bienvenida anónima, login/registro y regreso por logotipo, catálogo/detalle reales en lectura; panel y login/retorno con autenticación interceptada, sin guardar favorito automáticamente. No se enviaron escrituras al servidor ni se alteraron datos. No se ejecutó login real contra desarrollo.
- Capturas de escritorio (1440 px) y móvil (390 y 320 px) inspeccionadas: sin superposiciones, cortes ni desbordamiento horizontal. Tab comprobado sobre salto al contenido y logotipo; foco visible conservado. No es una auditoría completa de accesibilidad ni de todos los navegadores/dispositivos.
- Playwright completó los casos pero quedó esperando cerrar sus servidores en Windows. Se identificaron sus árboles de procesos y se cerraron únicamente los servidores creados por esa ejecución; tras ello terminó con código 0 y 3 passed (3,1 min). No se detuvieron servidores ajenos.
- Rutas y reproducción en bienvenida.md; consulta-publica.md actualizada. Sin migraciones, paquetes nuevos, cambios de base de datos, commit ni publicación. Implementación completada; queda fuera de esta verificación repetir autenticación real en navegador, pues escribiría sesión/last_login y esta etapa prohíbe modificar datos.

## Estado actual — ajuste de consulta pública (25 de octubre de 2026)

- Repositorio limpio comprobado en 3f11de4. Ya funcionaban consulta anónima de catálogo/detalle, filtros, paginación, reglas de publicación y enlaces públicos de cuenta. Conservados permisos y CSRF.
- Ajustados enlace oficial y aclaración de postulación externa; favorito anónimo dirige al login con retorno interno validado, sin guardar automáticamente. Se retiraron indicadores internos de revisión de opciones/requisitos en respuestas públicas.
- Comprobaciones reales: Django check sin incidencias; makemigrations --check --dry-run sin cambios. 73 pruebas backend aprobadas en test_becanexo_db con --keepdb y sin paralelismo (54,942 s), 59 frontend aprobadas (17,06 s); lint y build aprobados. Cero fallidas u omitidas.
- Navegador anónimo: 1 recorrido aprobado en Edge (6,2 s), catálogo y búsqueda, detalle y enlace oficial, acceso a login desde favorito, conservación de next tras recarga y favoritos protegidos. Cero solicitudes de escritura a la API. Login y retorno completos probados en integración frontend con API simulada; autenticación real comprobada en backend de pruebas. No se inició sesión contra desarrollo para evitar modificar last_login o sesiones persistidas.
- Primer intento de Playwright detenido por puerto 8000 ocupado. Se añadió playwright.public.config.js, limitado al recorrido público de lectura, para reutilizar servidores locales activos sin detenerlos. Captura del detalle público revisada. Los servidores del usuario permanecen intactos.
- Documentación en consulta-publica.md y contrato de favoritos actualizado. Sin migraciones, cambios de datos de desarrollo, cambios del respaldo, commit ni publicación. No hay comprobaciones solicitadas pendientes; el recorrido de navegador cubre Edge y no pretende sustituir pruebas de todos los navegadores.

## Estado actual — favoritos (25 de octubre de 2026)

- Estado inicial verificado: repositorio limpio en bc4844e; convocatorias revisadas y guardadas por el usuario. Leídos AGENTS, REL_FAVORITO del modelo/diccionario y referencias visuales de favoritas/detalle.
- Escritos modelo, API propia, controles de catálogo/detalle y /favoritos con navegación de postulante. La visibilidad se comparte con el catálogo; las oportunidades ocultas solo muestran un aviso y permiten quitar el favorito propio.
- Migración inicial generada y revisada: una CreateModel, tabla REL_FAVORITO con sus FK y restricción única. Django check aprobado y makemigrations --check --dry-run sin cambios. Se comprobó tabla ausente e historial pendiente en desarrollo; tras aprobar las pruebas se aplicó `favoritos.0001_initial` en becanexo_db y showmigrations confirmó [X]. No se borraron ni reconstruyeron tablas.
- Pruebas ejecutadas: 70 backend aprobadas en test_becanexo_db con --keepdb sin paralelismo (37,709 s), incluyendo las 62 anteriores; 37 frontend aprobadas (13,88 s). Cero fallidas, errores u omitidas. Lint y build aprobados.
- Recorrido `npm.cmd run test:e2e -- e2e/favorites.spec.js`: 1 aprobado (15,4 s). Guardar desde catálogo, recargar, abrir detalle, listar, cerrar sesión, abrir nueva sesión del mismo postulante, listar y quitar. Persistencia tras login real con contraseña comprobada además en backend. El navegador usa sesiones de fixture sin contraseñas, como el recorrido previo de convocatorias; no se afirma haber escrito credenciales en ese recorrido.
- Capturas de favoritos en 1440×1000 y 390×844 revisadas; sin desbordamiento móvil. Estado vacío capturado. No se repitieron los otros recorridos de navegador: sus módulos sí se incluyeron en las suites completas de backend/frontend.
- Datos: reutilizadas la oferta y cuentas DEMOSTRACIÓN existentes, sin cambiar sus credenciales ni last_login. Solo se creó y quitó el favorito propio de la prueba; no se borraron favoritos anteriores (el test comprueba su ausencia antes de guardar). Sesiones nuevas cerradas al terminar; el cierre repetido de una sesión ya cerrada devolvió el 403 esperado. Servidores locales detenidos por Playwright.
- Contrato y pasos manuales en [api-favoritos.md](api-favoritos.md). No hay pruebas solicitadas pendientes. Límites: comprobación visual en Edge, no auditoría completa de accesibilidad ni otros navegadores. La actualización entre pestañas requiere recargar/consultar otra vez; no hay sincronización en tiempo real. No se implementaron notificaciones, IA ni rastreo. Sin commit ni publicación; referencia conservada bc4844e.

## Registro histórico — convocatorias y catálogo (25 de octubre de 2026)

- Perfiles guardado en el commit local `5523eb8`; convocatorias sin commit.
- Se verificaron archivos parciales y ausencia de migraciones. Se conservaron modelos y contratos, y se añadieron API, servicios, auditoría y carga idempotente.
- Backend: 62 pruebas aprobadas, 0 errores/fallidas/omitidas, 35,170 s en test_becanexo_db con --keepdb sin paralelismo. Django check sin incidencias; makemigrations --check --dry-run sin cambios.
- Frontend: 30 pruebas aprobadas, lint sin incidencias y build aprobado. Gestión de oferentes, editor/listado administrativo, catálogo y detalle implementados. Errores por campo y conservación de entradas comprobados.
- Revisados el historial y la ausencia de las diez tablas nuevas antes de aplicar `convocatorias/0001_initial.py`: 10 CreateModel, 3 AddField y 16 AddConstraint, sin operaciones destructivas. Aplicada con éxito en becanexo_db; showmigrations confirma [X]. La revisión AST inicial incluyó por error swappable_dependency como operación; se corrigió para inspeccionar exclusivamente operations.
- Cargados catálogos dos veces: 2 tipos de beca y 13 contratos de requisitos, sin duplicados ni ofertas en el comando. Países/idiomas/áreas reutilizados.
- Navegador: 3 recorridos aprobados en Edge con backend real, 29,8 s. El nuevo recorrido creó entidad y convocatoria DEMOSTRACIÓN, opción con Ecuador/España, beneficio del 80 % de matrícula y condición documental externa. Publicó, consultó como postulante, editó, comprobó 404 mientras estaba pendiente y republicó, verificando el cambio.
- Se crearon dos cuentas DEMO específicas sin contraseñas utilizables y sin privilegios de Django Admin; las pruebas anteriores también crearon sus dos cuentas desechables habituales. No se modificaron credenciales ni cuentas previas. La demostración se reutiliza. Las sesiones nuevas del recorrido se cerraron.
- Ajustes visuales verificados: casillas de selección con tamaño correcto, espera de carga antes de capturar y paginación sin desbordamiento móvil. Se repitió únicamente offers.spec.js, reutilizando entidad, convocatoria y cuentas DEMO: aprobado en 18,3 s. Capturas finales de catálogo, detalle y administración revisadas a 1440 y 390 px; sin desbordamiento en las tres pantallas. Lint y build finales aprobados tras el ajuste CSS. Servidores de prueba detenidos al terminar.
- Datos conservados: una entidad DEMOSTRACIÓN, una convocatoria DEMOSTRACIÓN, una opción con dos destinos, un beneficio y un requisito externo. Las ejecuciones posteriores reutilizaron esos registros y agregaron únicamente eventos de sus ediciones/publicaciones y sesiones temporales cerradas al terminar. No se duplicaron las cuentas DEMO ni se cambiaron sus credenciales; el helper de repetición crea sesiones sin actualizar last_login.
- Adaptación de AUD_EVENTO, transiciones, endpoints, reglas y pasos manuales en [api-convocatorias.md](api-convocatorias.md). [ejecucion-local.md](ejecucion-local.md) actualizada. Revisión de patrones de secretos sin hallazgos; .env, entorno virtual, dependencias, respaldos y reportes excluidos; git diff --check sin errores.
- No quedan comprobaciones solicitadas pendientes. Límites: Edge de escritorio/móvil comprobado, no otros navegadores ni auditoría completa de accesibilidad/carga; HTTPS y operación distribuida pendientes de producción. Las referencias de fuente/configuración de AUD_EVENTO se añadirán con esos módulos, ampliando su restricción de objeto único. No se implementaron favoritos, IA, rastreo ni notificaciones. Convocatorias permanece sin commit; último commit 5523eb8, sin publicación.

## Registro histórico — perfil y preferencias (25 de octubre de 2026)

- Se conservó el trabajo parcial y el commit de autenticación `4cd2c1f`. El módulo perfiles permanece sin commit; no se publicó el repositorio.
- Implementadas las diez tablas del perfil v0.5, sus restricciones, API propia con sesiones/CSRF y catálogos de solo lectura. La propiedad se obtiene de la sesión; las modificaciones se serializan por usuario y actualizan la versión del perfil en la misma transacción.
- Implementadas `/perfil` y `/preferencias`: datos personales progresivos, formación, experiencia, idiomas, áreas, preferencias y destinos. Hay confirmación de eliminación, errores por campo y conservación de entradas ante errores. Los valores desconocidos se mantienen como NULL, distintos de False y cero.
- Se revisó el historial real antes de migrar: las tablas de perfiles no existían. Se generó `backend/perfiles/migrations/0001_initial.py` (10 CreateModel y 16 AddConstraint), se probó y se aplicó en `becanexo_db` con autorización. `showmigrations perfiles` confirmó `[X] 0001_initial`.
- Se ejecutó dos veces la carga idempotente: quedaron 249 países/territorios, 12 idiomas y 11 áreas amplias CINE-F. No se cambiaron credenciales ni el superusuario. Fuentes, cobertura y hash en `backend/perfiles/data/FUENTES.md`.

### Resultados ejecutados

- `manage.py check`: sin incidencias. `manage.py makemigrations --check --dry-run`: sin cambios pendientes.
- `manage.py test usuarios perfiles --keepdb --verbosity 2`: **46 aprobadas**, 0 fallidas, 0 errores y 0 omitidas, en 29,725 s en la última ejecución. Se usó `test_becanexo_db`, distinto de desarrollo, sin paralelismo del ejecutor. Una prueba específica usa dos conexiones para comprobar la actualización concurrente de versión.
- Frontend: `npm.cmd run lint` y `npm.cmd run build` aprobados; `npm.cmd test`: **22 aprobadas** (13 de autenticación y 9 de perfil).
- `npm.cmd run test:e2e`: **2 recorridos aprobados** en Edge y backend real, en 21,6 s. Se comprobó persistencia tras recarga, edición, cancelación y confirmación de eliminación, sesión/CSRF y ausencia de desbordamiento móvil. Se revisaron capturas de escritorio y móvil.
- Los recorridos crearon dos cuentas desechables nuevas en desarrollo; una conserva su perfil de prueba. Solo se eliminó la experiencia creada por ese mismo recorrido. No se modificaron cuentas anteriores. Los servidores de Playwright se detuvieron al terminar.
- Se corrigió un selector ambiguo de la prueba de idioma. Se reforzaron además la normalización de textos opcionales con espacios a NULL y el rechazo de campos en DELETE; después se repitieron las 46 pruebas backend con éxito.

### Límites y siguientes etapas

- No quedan pruebas solicitadas pendientes. La verificación de navegador cubre Edge en escritorio/móvil; faltan otros navegadores y una auditoría completa de accesibilidad.
- El contrato, diferencias con el ER (incluido varchar(2) para país y el dominio de modalidades), reglas y comprobación manual están en [api-perfil.md](api-perfil.md). Los catálogos de idiomas y áreas tienen cobertura inicial limitada y documentada.
- No se implementaron convocatorias, recomendaciones, rastreo ni notificaciones. HTTPS, cookies Secure, despliegue SPA y limitación distribuida siguen pendientes de producción.

## Registro histórico — frontend inicial (24 de octubre de 2026)

- Se inspeccionó frontend/ y estaba vacío. Se creó React con Vite, JavaScript/JSX y Tailwind CSS, con package-lock.json. Se priorizó Node portable 24.22.1 en el PATH de cada proceso; no se modificó el PATH global ni se instalaron herramientas globales.
- Implementadas /login, /registro e /inicio. Formularios con etiquetas, autocomplete, foco visible, errores de campos, carga y bloqueo de doble envío. Registro dirige al login con confirmación; inicio muestra solo nombre y rol reales y permite cerrar sesión.
- Cliente de API centralizado con rutas relativas, cookies, CSRF en memoria, renovación tras login y tratamiento de 204, 400, 403, 429, errores de red y servidor. No hay almacenamiento de credenciales/tokens en localStorage/sessionStorage ni mocks fuera de pruebas.
- Contexto de autenticación consulta me al cargar y espera antes de redirigir; un fallo de conexión o 5xx muestra reintento, no se confunde con una sesión ausente. La protección del backend se conserva.
- Se leyeron y visualizaron login/registro del PDF (páginas 3–4). Se respetaron colores, tipografía Inter local y disposición del panel y formulario, adaptando textos y quitando funciones simuladas. Se revisaron capturas reales en escritorio y móvil; no hay estadísticas ni recomendaciones ficticias.
- Vite está configurado en 127.0.0.1:5173, strictPort, proxy /api hacia 127.0.0.1:8000 y Origin conservado. Django lee DJANGO_CSRF_TRUSTED_ORIGINS del entorno (lista vacía por defecto); solo se configura http://127.0.0.1:5173 para la ejecución local. No hay CORS abierto, excepciones CSRF ni cambios en credenciales.
- Archivos: proyecto frontend completo, incluidos src/api, src/auth, src/components, src/pages, pruebas Vitest y Playwright; ajustes en backend/config/settings.py, backend/.env.example, backend/usuarios/test_api.py y .gitignore. Nueva guía docs/ejecucion-local.md y actualización del contrato de autenticación.

### Verificación del frontend inicial

- npm run lint: aprobado, sin errores.
- npm run build: aprobado, genera dist/.
- npm test: **13 pruebas aprobadas**, con fetch simulado exclusivamente en pruebas.
- manage.py check: sin incidencias; makemigrations --check --dry-run: No changes detected.
- manage.py test usuarios --keepdb --verbosity 2: **30 aprobadas**, 0 fallidas/errores/omitidas, sobre test_becanexo_db, en 23,412 segundos. Incluye la prueba nueva que comprueba CSRF con el origen local Vite.
- npm run test:e2e: **1 prueba de recorrido completo aprobada** en Edge sin ventana, con Django y PostgreSQL reales; registro 201, login 200, restauración de sesión por me tras recarga, logout 204 y retorno al login al intentar acceder sin sesión. Se confirmó Origin http://127.0.0.1:5173 y almacenamiento web vacío. Vistas revisadas a 1440×1000 y 390×844, sin desbordamiento horizontal en móvil.
- La primera ejecución de navegador se detuvo después de login por consultar Origin con el listado reducido headers() de Playwright. Se corrigió la comprobación usando allHeaders(); la ejecución posterior aprobó. No se cambió ni falsificó el Origin de la aplicación.
- Las dos ejecuciones crearon **dos cuentas desechables nuevas** en becanexo_db (nombre «Verificación desechable», correo e2e-UUID@example.com). Se conservaron; no se eliminó ni modificó ningún usuario previo ni el superusuario. Las pruebas unitarias del backend siguen usando únicamente su base de pruebas.
- Se preservó el commit de referencia fb73f9a: no se hicieron commits ni publicaciones. Los servidores utilizados por Playwright se detuvieron al terminar.

### Pendientes registrados al finalizar el frontend inicial

- Ampliar la verificación a otros navegadores y una auditoría de accesibilidad completa. No se implementaron los demás módulos del alcance.
- Antes de producción: HTTPS/cookies Secure, política de origen y alojamiento SPA, límites compartidos y demás configuración de despliegue.
- Los comandos exactos para abrir el aplicativo, repetir las pruebas y el efecto de las cuentas desechables están en docs/ejecucion-local.md.

## Registro histórico — API de autenticación (24 de octubre de 2026)

- El responsable confirmó que aplicó las migraciones en becanexo_db y que existe un superusuario con acceso a /admin/. Esta tarea no modificó esa cuenta ni sus credenciales y no ejecutó migraciones sobre desarrollo.
- Implementados GET /api/auth/csrf/, POST /api/auth/registro/, POST /api/auth/login/, GET /api/auth/me/ y POST /api/auth/logout/ con Django REST Framework y sesiones nativas.
- Registro restringido a nombre, email, password y password_confirm, sin privilegios ni creación de perfil, con validadores de contraseña y tratamiento transaccional de duplicados en PostgreSQL. No inicia sesión automáticamente.
- CSRF verificado explícitamente también para anónimos; login devuelve token renovado. Me devuelve solo id, email, nombre y rol. Logout invalida la sesión. Todas las respuestas llevan directivas de no caché.
- Cookies de sesión HttpOnly y SameSite=Lax; Secure configurable para sesión y CSRF, desactivado por defecto para HTTP local. No se habilitó CORS ni se incorporaron JWT o excepciones csrf_exempt.
- Límites configurables por REMOTE_ADDR: registro 5/hora y login 10/minuto; contadores LocMemCache separados por operación. X-Forwarded-For se ignora. Esta protección es local al proceso y no garantiza resistencia a ataques ni conteos exactos bajo concurrencia.
- Archivos nuevos: backend/usuarios/api.py, serializers.py, throttles.py, urls.py y test_api.py, además de docs/api-autenticacion.md. Modificados backend/config/settings.py, backend/config/urls.py, backend/.env.example y esta documentación. Modelo, migración y pruebas previas se conservaron.

### Resultados de esta etapa

Antes de las pruebas se confirmó el destino test_becanexo_db, distinto de becanexo_db y sin TEST.MIRROR. Comandos ejecutados desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios --keepdb --verbosity 2
```

Los tres finalizaron con código 0. Check no identificó incidencias y makemigrations informó No changes detected. Las **29 pruebas aprobaron: 0 fallidas, 0 errores y 0 omitidas**, en 55,316 segundos. Incluyen las 16 anteriores y 13 nuevas de API con CSRF real. El ejecutor confirmó test_becanexo_db existente, sin migraciones pendientes, y la conservó al terminar; no se utilizó paralelismo.

Se verificaron registro/hash, validaciones, duplicados mediante el conflicto real de PostgreSQL, rechazo de privilegios, login y me, mensajes genéricos, usuarios inactivos, acceso anónimo, CSRF ausente/inválido y origen ajeno, rotación del token, logout e invalidez de la sesión anterior, métodos rechazados, 429 y aislamiento de contadores, cookies y no caché, y respuestas sin contraseñas ni hashes. No fue necesario debilitar ni corregir las pruebas anteriores.

### Pendientes registrados al finalizar la API

- Preparar HTTPS y configurar ambas cookies Secure antes de desplegar; decidir el origen/proxy del futuro frontend y una estrategia de límites compartidos si hay varios procesos. La limitación local no reemplaza controles operativos frente a abuso.
- No se realizaron pruebas de carga concurrente ni se ejecutó el ejemplo manual contra desarrollo. El comportamiento de la API se verificó con PostgreSQL de pruebas.
- Implementar los demás módulos del alcance por etapas; no se crearon frontend, perfiles ni convocatorias. No se hicieron commits ni publicaciones.

El contrato, códigos de respuesta, renovación CSRF, limitaciones e instrucciones reproducibles están en `api-autenticacion.md`.

## Registro histórico — etapa 2 (24 de octubre de 2026)

- Incorporados y revisados los documentos de `docs/Modelo/`: modelo lógico v0.5, diccionario y reglas. También está disponible el PDF de interfaces en `docs/diseno/`.
- Implementada la app `backend/usuarios`: Usuario basado en AbstractBaseUser y PermissionsMixin, manager personalizado y administración con formularios de Django. No existe username en el modelo.
- Configurados `AUTH_USER_MODEL`, el backend ModelBackend con búsqueda normalizada mediante el manager, `rest_framework` y `usuarios` en INSTALLED_APPS.
- Mapeados los siete campos de MAE_USUARIO, incluido password → password_hash e is_active → activo. Agregadas las restricciones de correo, rol y campos no vacíos y los campos técnicos de Django; detalle en `decisiones-autenticacion.md`.
- Confirmada la existencia de `backend/usuarios/migrations/0001_initial.py`: crea MAE_USUARIO con sus mapeos de columnas y restricciones de unicidad de correo, rol y campos no vacíos. Se aplicó únicamente en la base de pruebas mediante el ejecutor de Django; sigue sin aplicarse en desarrollo.
- Las 16 pruebas están ejecutadas y aprobadas: siete sin persistencia y nueve con PostgreSQL. Cero fallidas, cero errores y cero omitidas.
- No se implementaron endpoints, perfiles, convocatorias ni frontend. No se modificaron credenciales o permisos de PostgreSQL, ni se ejecutaron migrate, createsuperuser, commits o publicaciones.

### Comprobaciones de la etapa 2

Ejecutadas desde la raíz con `.\.venv\Scripts\python.exe`:

- `backend/manage.py makemigrations usuarios`: código 0; generó 0001_initial.py. El comando puede consultar el historial de migraciones, pero no aplica cambios al esquema.
- `backend/manage.py check`: código 0; sin incidencias.
- `backend/manage.py makemigrations --check --dry-run`: código 0; `No changes detected`.
- `backend/manage.py test usuarios.tests.UsuarioSinBaseTests --verbosity 2`: siete pruebas, todas OK; omitió expresamente la preparación de la base de datos.
- `git check-ignore -v --non-matching backend/usuarios/migrations/0001_initial.py`: no hay regla que excluya la migración.

### Pendientes registrados al finalizar la etapa 2

- Revisar y autorizar la primera aplicación de migraciones en la base de desarrollo en una etapa posterior.
- Implementar endpoints de registro, inicio y cierre de sesión con CSRF, controles de acceso y pruebas. El registro público no deberá aceptar rol ni privilegios del cliente.
- Implementar los demás módulos del alcance por etapas, de acuerdo con el modelo e interfaces; preparar Node 24 LTS antes del frontend.

### Verificación completa del módulo usuarios (24 de octubre de 2026)

La base `test_becanexo_db` fue creada manualmente por el responsable con propietario `becanexo_app`. Se configuró explícitamente `DATABASES["default"]["TEST"]["NAME"] = "test_becanexo_db"` en settings.py, manteniendo el nombre de desarrollo leído desde el entorno. Antes de ejecutar se comprobó que el nombre efectivo de desarrollo era `becanexo_db`, que ambos nombres eran diferentes y que no había TEST.MIRROR.

Se revisaron los módulos de usuarios: AppConfig no define ready() y las operaciones de persistencia están dentro de métodos de TestCase. Las pruebas sin base utilizan SimpleTestCase. Además, se ejecutaron django.setup() y la importación de usuarios.tests con ensure_connection bloqueado para detectar cualquier intento de conexión: ambos terminaron correctamente sin intentar conectarse.

Comandos ejecutados desde la raíz, todos con código de salida 0:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios --keepdb --verbosity 2
```

- check: sin incidencias.
- makemigrations: `No changes detected`; no fue necesario regenerar la migración inicial existente.
- test: 16 ejecutadas, 16 aprobadas, 0 fallidas, 0 errores, 0 omitidas; duración informada de las pruebas: 15,135 segundos.
- Ejecución secuencial, sin --parallel. Django confirmó el uso de la base existente `test_becanexo_db` y aplicó allí las migraciones de usuarios y las dependencias del framework.
- --keepdb conserva la base de pruebas y su esquema para posteriores ejecuciones. Las pruebas TestCase aíslan sus escrituras mediante transacciones; esta opción no convierte la base de desarrollo en base de pruebas.

No se encontraron defectos que requirieran modificar el modelo, manager, formularios, Admin o pruebas. No hubo errores de conexión ni permisos. Solo se ajustó la configuración de la base de pruebas y la documentación; no se modificó .env, no se cambiaron permisos ni credenciales y no se ejecutó migrate sobre becanexo_db ni createsuperuser. No quedan pruebas pendientes de esta suite; los endpoints y sus pruebas de integración con sesiones/CSRF siguen fuera de esta etapa.

## Registro histórico — etapa 1

### Estado inspeccionado el 23 de octubre de 2026

- Existe el proyecto Django en `backend/`, con configuración en `backend/config/` y `manage.py`.
- Existe el entorno virtual `.venv` en la raíz. Las dependencias están declaradas en `backend/requirements.in` y fijadas en `backend/requirements.txt`: Django 5.2, Django REST Framework, psycopg y django-environ.
- `settings.py` carga `backend/.env` y lee `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT`. La clave no tiene respaldo en código; DEBUG vale `False` si no se define; el puerto tiene respaldo 5432.
- Están configuradas las aplicaciones iniciales de Django y el middleware de sesiones, autenticación y CSRF. La ruta inicial de administración está declarada; esto no acredita que exista un administrador ni que la administración esté operativa sin migraciones.
- Django REST Framework está declarado como dependencia, pero todavía no está integrado en `INSTALLED_APPS` ni existen endpoints del proyecto.
- No hay modelos de negocio ni implementación de autenticación por correo. Las carpetas `frontend/` y `docs/` estaban vacías al iniciar esta tarea.
- Git está inicializado y los archivos del proyecto todavía están sin seguimiento. No se realizan commits en esta etapa.

El responsable informa que PostgreSQL local ya está conectado a `becanexo_db` con el usuario `becanexo_app` y que no se han ejecutado migraciones. Esta tarea no consulta ni modifica datos y no verifica la conexión mediante una consulta SQL. `manage.py check` por sí solo no demuestra conectividad con PostgreSQL.

### Cambios de la etapa 1

- Se conserva `settings.py` porque cumple los requisitos solicitados.
- Se añade `backend/.env.example` con las variables necesarias y los campos de clave y contraseña vacíos; debe completarse localmente para utilizarlo.
- Se amplía `.gitignore` para temporales, cachés, dependencias y respaldos; se conserva la excepción de `.env.example` y no se excluyen migraciones.
- Se añaden las reglas de colaboración en `AGENTS.md` y el alcance en `docs/alcance.md`.
- No se modifica `.env`, ni se crean modelos, migraciones, endpoints o frontend. No se ejecuta `migrate`, ni se instalan herramientas globales o se publica el repositorio.

### Comprobaciones de la etapa 1

Comprobaciones ejecutadas el 23 de octubre de 2026:

- `.\.venv\Scripts\python.exe backend/manage.py check`: finalizó con código 0 y `System check identified no issues (0 silenced).` No se ejecutaron migraciones.
- `git check-ignore -v backend/.env`: confirmó que la regla `.env` de `.gitignore` excluye el archivo privado, sin mostrar su contenido.
- `git check-ignore -v --non-matching backend/.env.example backend/futura_app/migrations/0001_initial.py`: confirmó la excepción `!.env.example` y la ausencia de una regla de exclusión para la ruta hipotética de migración. No se creó ese archivo.
- `git status --short`: muestra los archivos del proyecto sin seguimiento; no se ha creado ningún commit en esta tarea.

No se ejecutaron pruebas funcionales; todavía no se han implementado funciones de negocio. La revisión de configuración se realizó sin exponer valores privados.

### Pendientes registrados al finalizar la etapa 1

- Incorporar y revisar el modelo de datos y las interfaces actualizados.
- Resolver el modelo de autenticación por correo antes de la primera migración, incluidos roles, permisos y pruebas de autenticación, autorización y CSRF.
- Documentar las diferencias del ER respecto de las tablas auxiliares de Django.
- Implementar por etapas los módulos del alcance, sus validaciones y pruebas; crear y aplicar migraciones cuando corresponda a una tarea autorizada.
- Integrar Django REST Framework y desarrollar los endpoints según el diseño.
- Preparar Node 24 LTS y posteriormente el frontend React con Vite y Tailwind CSS. La versión Node 25 es información suministrada por el responsable, no comprobada en esta tarea.
- Implementar el rastreo, la recomendación local, las reglas de elegibilidad, las explicaciones, las notificaciones y la supervisión.
