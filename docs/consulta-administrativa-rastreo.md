# Consulta administrativa del rastreo

## Revisión administrativa disponible — 29/10/2026

La bandeja ahora permite **registrar revisiones** en el detalle, además de consultar. Las secciones posteriores a este apartado documentan la etapa inicial de solo lectura y sus pruebas históricas; esa limitación ya no describe el endpoint de revisión. Ningún GET escribe datos.

Ruta: `http://127.0.0.1:5173/gestion/rastreo/publicaciones/:id`. Publicaciones existentes: `/gestion/rastreo/publicaciones/1` y `/gestion/rastreo/publicaciones/2`. No es necesario lanzar un rastreo. Iniciar Vite/Django con los comandos locales habituales; el recorrido automatizado cierra su propio Vite.

### API de revisión

`GET|POST /api/gestion/rastreo/publicaciones/{id}/versiones/{version_id}/revisiones/`

Solo administrador activo con sesión Django. POST exige CSRF; se reutilizan AuthView, JSONParser y no-store. No hay PATCH/DELETE. El actor procede exclusivamente de request.user. POST no acepta parámetros de consulta ni campos fuera del contrato.

GET acepta page/page_size (1–50, predeterminado 12), devuelve count/page/page_size/results y además `vigentes`, `version_id`, `numero`, `ultima_observada`. Historial descendente por fecha/ID; vigentes excluye filas sustituidas. `ultima_observada` compara con la última observación exitosa, no el número máximo de versión. IDs globales y número de versión no son intercambiables. Las revisiones incluyen ID, dimensión, decisión, motivo, fecha, versión, evidencia, sustituye_id, detalle y administrador (ID/nombre), nunca correo, hashes de contraseña ni rutas físicas.

POST requiere:

```json
{
  "dimension": "documental",
  "decision": "pendiente",
  "motivo": "Justificación tras examinar la evidencia",
  "evidencia_id": 123,
  "sustituye_id": null,
  "clave_accion": "UUID nuevo de esta acción"
}
```

Ejemplo de contrato, **no para ejecutarlo con esos valores**. evidencia_id es REL_VERSION_DOCUMENTO.id, expuesto como `evidencia_id` por el listado de documentos; el `id` de ese listado sigue siendo el documento descargable. Extracción exige evidencia_id null. Documental y oferente exigen evidencia exacta de la versión. Oferente requiere además `tipo_oferente` y `referencia`; aprobación solo para entidad_ecuatoriana respaldada. Convenio/no_determinado permiten pendiente/rechazada, nunca aprobada. Motivo: texto no vacío, máximo 5000; referencia: texto no vacío, máximo 2000.

Respuestas: 201 creada; 200 reintento idéntico o consulta; 400 campos/relaciones inválidos; 403 sesión/rol/actividad/CSRF; 404 versión inexistente o ajena; 405 método no permitido; 409 revisión anterior obsoleta o clave reutilizada con otro contenido. Rectificar usa el ID vigente en sustituye_id; conserva versión/dimensión/evidencia. Consultar el historial después de un 409 no guarda nada: se requiere otra confirmación explícita.

### Recorrido manual

1. Entrar con una sesión administradora y abrir Rastreo → Abrir publicación. Comprobar la versión seleccionada y la indicación de última observación exitosa o evidencia histórica.
2. Examinar información extraída, advertencias y documentos. HTTP 200 y extracción completa no son aprobaciones. Descargar es consulta; revisar exige examinar el contenido.
3. En Revisiones administrativas, comprobar pendientes sin filas ficticias y decisiones vigentes. Abrir Registrar revisión, elegir dimensión y, cuando corresponda, documento exacto. El destino y la revisión que se sustituiría se muestran antes de guardar.
4. Introducir decisión y justificación. **Guardar modifica el historial real y no debe usarse como ensayo sobre SIAU sin examinar la evidencia**. Para inspeccionar solamente el formulario, usar Cancelar. Las pruebas automatizadas guardan exclusivamente en test_becanexo_db o en una API simulada.
5. Tras una revisión legítima, comprobar confirmación, historial, autor, fecha y decisión vigente. Rectificar registra otra fila; no elimina la anterior. Si otro administrador decidió mientras tanto, conservar el texto, actualizar historial, revisar el conflicto y confirmar de nuevo.

No se publican ni vinculan convocatorias, no se resuelven incidencias y una decisión histórica no aprueba otra versión. Las advertencias almacenadas del extractor son históricas y no se reescriben cuando se revisa un documento. Fechas y vigencia de la oportunidad permanecen separadas de la revisión.

Pruebas y respaldo de esta etapa: [avance](avance.md). Modelo efectivo: [suplemento](Modelo/Revision_administrativa_rastreo.md).

## Registro histórico: etapa de solo consulta

Implementada el 28/10/2026 sobre el commit 8ee1fc7 como etapa inicial de **solo consulta**: entonces no iniciaba rastreos, no modificaba fuentes, no aprobaba documentos, no resolvía incidencias ni creaba, vinculaba o publicaba convocatorias. Hoy el panel también inicia capturas manuales, el rastreo tiene corrida programada diaria, las fichas en alcance generan borradores privados con llenado automático y la publicación se hace con «Validar y publicar». No modifica modelos ni añade migraciones.

## Rutas de interfaz

Base local: `http://127.0.0.1:5173`.

| Ruta | Contenido |
| --- | --- |
| `/gestion/rastreo` | Publicaciones detectadas, búsqueda por título/URL y selector de fuente por nombre |
| `/gestion/rastreo/publicaciones/:id` | Origen, versiones, datos extraídos, advertencias, evidencia exacta e historial de observaciones |
| `/gestion/rastreo/ejecuciones` | Ejecuciones paginadas y contadores |
| `/gestion/rastreo/ejecuciones/:id` | Estado, contadores, accesos HTTP e incidencias paginadas |

El administrador tiene un enlace **Rastreo** en Inicio y en la navegación lateral. Postulantes no ven ese acceso y son redirigidos a Inicio; visitantes son dirigidos al login. El cierre de sesión existente permanece accesible en escritorio y móvil. Estas barreras visuales no sustituyen los permisos del servidor.

## Endpoints y permisos

Prefijo: `/api/gestion/rastreo/`. Todos requieren **usuario autenticado, activo y con rol administrador**, independientemente de is_staff. Reutilizan AuthView, autenticación por sesión y protección CSRF existentes; respuestas no-store. No se añade autenticación por identificador ni tokens nuevos. Métodos disponibles: GET y OPTIONS. No existen operaciones de escritura.

| GET, relativo al prefijo | Respuesta |
| --- | --- |
| `fuentes/` | ID y nombre, paginados |
| `publicaciones/` | Fuente, título (o ruta URL si no hay título), origen, detecciones y versión observada |
| `publicaciones/{id}/` | Información de una identidad detectada |
| `publicaciones/{id}/versiones/` | Versiones registradas y fechas de creación, paginadas |
| `publicaciones/{id}/versiones/{version_id}/` | Datos, texto, advertencias y versiones técnicas del extractor/contrato |
| `publicaciones/{id}/versiones/{version_id}/documentos/` | Documentos exactos de esa versión, paginados |
| `publicaciones/{id}/observaciones/` | Fecha, resultado, versión y ejecución, paginados |
| `ejecuciones/` | Ejecuciones y contadores, paginados |
| `ejecuciones/{id}/` | Ejecución, incluidos los registros sin publicaciones |
| `ejecuciones/{id}/accesos/` | Intentos HTTP, resultado y relaciones disponibles, paginados |
| `ejecuciones/{id}/incidencias/` | Código, gravedad, fecha y relaciones disponibles, paginados |
| `documentos/{id}/descarga/` | Evidencia almacenada como archivo adjunto |

Listados: `page` entero >= 1; `page_size` entre 1 y 50, predeterminado 12. Respuesta `{count,page,page_size,results}`. Una página fuera de los resultados devuelve lista vacía. Publicaciones admite además `q` (máximo 200 caracteres, título observado/URL) y `fuente` (ID positivo). Parámetros desconocidos/repetidos, tamaños inválidos e identificadores fuera de rango se rechazan. La interfaz carga los nombres desde fuentes/ y envía su ID en el filtro. Si hay más de 50 fuentes ofrece Más fuentes; incluye carga, error y reintento, sin nombres codificados manualmente.

Códigos: 200 consulta/descarga correcta; 400 parámetros inválidos; 403 falta de autorización o CSRF en intentos de escritura; 404 objeto inexistente o versión ajena a la publicación; 405 método no admitido una vez superados los controles de autenticación/CSRF; 409 evidencia ausente, inconsistente o ruta insegura. La interfaz presenta error y reintento sin mostrar éxito ficticio.

## Significado de la información

- Una **publicación detectada** es evidencia de una fuente, no una convocatoria del catálogo. Puede no tener título, versión o convocatoria canónica; no se completan huecos inventando datos.
- La versión predeterminada se obtiene de la **última observación exitosa**, ordenada por observada_en e id para desempatar. A→B→A vuelve a mostrar A aunque B tenga un ID/número mayor. La lista de versiones permite consultar B por separado.
- Primera/última detección, creación de versión, observación e inicio/fin de ejecución son fechas técnicas distintas de las fechas de la beca. Los cierres declarados con precisión de día no se convierten a una hora inventada.
- Los datos actuales proceden del extractor HTML; se muestran como texto escapado, incluidas ambigüedades y advertencias. No se ejecuta HTML ni se incrusta el contenido descargado. Los PDF se identifican y descargan: no se presentan notas manuales como extracción automática ni se afirma lectura automática completa de sus requisitos.
- El estado de la ejecución se muestra como **Completada** (dominio `finalizada`), **Completada con avisos** cuando solo hay incidencias de gravedad aviso, **Parcial** únicamente por fallos reales (red, HTTP inesperado ≥ 400, error de análisis o extracción) y **Fallida**. Alcanzar el tope de fichas por corrida, la rotación del índice y los enlaces de bases fuera de la lista cerrada (`BASE_NO_PERMITIDA`) son avisos por diseño y no degradan el estado. **Revisión documental pendiente** continúa pendiente aunque HTTP sea 200 o la extracción HTML sea completa.
- `GET ejecuciones/<id>/incidencias/` admite los filtros `gravedad` (`error` o `aviso`) y `codigo`, pagina de 25 por defecto (máximo 50) y añade `resumen`: los grupos por código y gravedad con su contador (por ejemplo, `BASE_NO_PERMITIDA` aviso ×12), calculados sobre toda la ejecución. `GET ejecuciones/<id>/accesos/` también pagina de 25 por defecto. El detalle de la ejecución incluye `incidencias_error` e `incidencias_aviso`.
- En la interfaz, el detalle de ejecución muestra dos pestañas con contador, **Accesos** e **Incidencias**, y una sola lista a la vez. Los accesos aparecen como filas compactas (tipo, HTTP, estado del documento, URL truncada con la dirección completa al pasar el cursor, hora y publicación). Las incidencias se agrupan por tipo y gravedad con su contador, se despliegan bajo demanda y se filtran por gravedad (todas, error o aviso). El paginador «1–25 de N» solo aparece cuando hay más de una página.
- La pantalla de Rastreo tiene dos pestañas: **Publicaciones detectadas** y **Ejecuciones**. La pestaña «Candidatos del índice» se retiró por redundante (casi todos sus registros ya son publicaciones detectadas con borrador) y la ruta antigua `/gestion/rastreo/candidatos-indice` redirige a `/gestion/rastreo`. Una ejecución de metadatos del índice muestra solo su resumen: candidatos registrados y el aviso de que no se descargaron fichas. El modelo `CandidatoIndice`, sus datos y el endpoint `GET candidatos-indice/` se conservan sin cambios como registro de auditoría.
- Accesos cuenta intentos; documentos distintos cuenta IDs documentales únicos usados por esa ejecución. No equivale a documentos nuevos. `descargado` en un acceso significa documento nuevo conservado; `reutilizado` significa bytes ya almacenados. Versiones nuevas y observaciones sin cambios son contadores separados de publicaciones observadas.
- Las incidencias exponen código y gravedad, no mensajes técnicos crudos, rutas, configuración privada ni trazas. La interfaz convierte códigos conocidos a etiquetas y permite consultar el resto sin resolución editorial.

## Evidencia y consultas seguras

La descarga recibe únicamente un ID. El servidor resuelve la clave derivada del SHA-256, confina la ruta a RASTREO_STORAGE_ROOT, rechaza enlaces de directorio/archivo y verifica tamaño/huella. Envía los bytes comprobados como `application/octet-stream`, Content-Disposition attachment, nosniff y CSP sandbox/default-src none. El frontend descarga un blob, sin iframe ni inserción HTML. La raíz documental no se sirve como estático y no aparece en JSON, errores o nombres de descarga.

Cada recurso y subrecurso verifica autorización. Las FK de versión/publicación se contrastan; no basta con conocer un ID. Listados limitados y consultas con select_related/subconsultas/agregados evitan N+1; la prueba de listado controla un máximo de cinco consultas incluyendo sesión/usuario. El detalle trae una sola versión, dentro de los límites de evidencia existentes; documentos individuales están limitados por el modelo a 8 MiB.

No se escribe auditoría de lectura ni se altera historial. No se incorporan herramientas externas, paquetes nuevos, migraciones, cambios de credenciales o permisos.

## Comprobación manual con los datos existentes

1. Con Django en `127.0.0.1:8000` y Vite en `127.0.0.1:5173`, inicia sesión normalmente con tu cuenta administradora y abre **http://127.0.0.1:5173/gestion/rastreo**. También puedes entrar desde Inicio → Rastreo.
2. Deben aparecer dos publicaciones de SIAU, fuente ID 1. Busca «Productivo» o selecciona SIAU en Fuente. Una búsqueda inexistente debe mostrar vacío. Con dos registros no habrá segunda página: la paginación múltiple se verificó con datos sintéticos.
3. Abre `/gestion/rastreo/publicaciones/1` (Jóvenes) y `/gestion/rastreo/publicaciones/2` (Productivo). Cada una tiene versión número 1, IDs 1 y 2 respectivamente. Examina advertencias y fechas, y despliega datos técnicos de los documentos. No hay aprobación ni vínculo canónico.
4. La publicación 1, versión número 1 (ID global 1), referencia HTML 8 y PDF 4; la publicación 2, versión número 1 (ID global 2), referencia HTML 9 y PDF 6. Descargar evidencia debe guardar un adjunto. La aplicación no debe mostrar/ejecutar el HTML descargado. No alteres archivos reales para probar errores: esos casos están cubiertos en temporales de pruebas.
5. Abre `/gestion/rastreo/ejecuciones/1`: debe conservar sus seis accesos, seis documentos distintos y cero publicaciones/versiones/observaciones asociadas. No se reconstruyó su historia.
6. Abre `/gestion/rastreo/ejecuciones/2`: seis accesos HTTP 200, seis documentos distintos, dos publicaciones observadas y dos versiones nuevas. Los avisos 3/4 son revisión documental pendiente. Esta ejecución reutilizó tres documentos y almacenó tres nuevos; nueve documentos existen en total.
7. En ventana privada, la ruta de interfaz debe dirigir al login y `/api/gestion/rastreo/documentos/8/descarga/` rechazar el acceso. Con postulante, no debe aparecer el menú Rastreo ni autorizarse la API. Comprueba cierre de sesión, teclado y vista móvil sin modificar cuentas.

No es necesario ejecutar migrate, rastreo ejecutar ni previsualizar_siau para comprobar esta bandeja.

## Resultados efectivamente terminados

- Backend final: **9 pruebas aprobadas**, 14,737 s, cero fallidas/omitidas. `.\.venv\Scripts\python.exe backend/manage.py test rastreo.test_api --keepdb --verbosity 2`, secuencial, exclusivamente test_becanexo_db y documentos sintéticos en TemporaryDirectory. Incluye sesiones Django establecidas con force_login en pruebas, administradores/inactivos/postulantes/anónimos, pertenencia, A→B→A, ejecución sin publicaciones, título ausente, adjunto HTML, archivo corrupto/ausente, confinamiento, límites y ausencia de escrituras. Se repitió porque el resultado de la suite ampliada de siete a nueve no se había recuperado tras la interrupción.
- Frontend: **41 aprobadas** en Crawling.test.jsx, App.test.jsx y PublicAccess.test.jsx (12,07 s), antes de la reanudación; no cambió código de interfaz después y no se repitieron innecesariamente. Corrigida una expectativa inicial del test que buscaba navegación lateral en la página Inicio del postulante.
- Navegador Edge/Playwright final: **3 aprobadas**, 10,4 s. Comando desde frontend, con Node 24 en PATH: `npm.cmd run test:e2e -- --config playwright.crawling.config.js`. El primer recorrido cubre 1440, 390 y 320 px, foco/teclado, texto seguro, versiones e historial. El ampliado cubre 1440/390 px, entrada desde Inicio, filtros, paginación, vacío, error/reintento, selección A/B, descarga de adjunto HTML sin ejecutarlo, ejecuciones/accesos/incidencias, menú y cierre de sesión visible. Capturas revisadas en escritorio y móvil sin desbordamientos ni superposiciones observadas. Ambos recorridos administrativos usan **API y sesión simuladas**, no cuentas reales. La simulación de error se mantuvo hasta pulsar reintento para no consumirla con el doble montaje de StrictMode; no se relajaron las aserciones.
- La tercera prueba HTTP usa **backend real anónimo**: publicaciones y descarga devuelven 403. No inicia sesión ni modifica cuentas.
- **18 consultas con datos y documentos reales** devolvieron 200 en transacción PostgreSQL READ ONLY, con autenticación administrativa inyectada en memoria mediante APIRequestFactory. No es login web ni sesión real. Huellas de **34 tablas de negocio/rastreo** iguales antes/después. Script local ignorado `outputs/rastreo/verificar_bandeja.py`; no copia filas ni imprime datos personales. Integridad: nueve documentos, cero problemas/eliminados. Se revalidó al completar.
- Django check sin incidencias; makemigrations --check --dry-run sin cambios; migrate --plan sin operaciones. Ninguna migración nueva/aplicada en esta tarea. Lint final correcto; build correcto antes de reanudar (64 módulos); los cambios posteriores fueron pruebas/documentación, sin alterar código compilado.

Limitación de verificación: no se hizo login interactivo en navegador con una cuenta real administradora. Queda la comprobación manual del paso 1 con tu sesión; no se modificó ninguna cuenta para automatizarla. No se ensayó restauración completa del respaldo informado `D:\Respaldos_BecaNexo\becanexo_bloque2_20261028_053424`, ni se modificó ese respaldo. Revisión editorial, vinculación/publicación y ejecución de rastreo desde la interfaz pertenecen a futuras etapas.


## Corrección visual y de controles — 28/10/2026

### Causas reproducidas

- El formulario heredaba flex-direction: column del estilo global de form. El flex-basis: 14rem de cada etiqueta se aplicaba verticalmente: altura medida de 640,8 px a 1440×900. Además, los campos no pertenecían a .field y quedaban sin borde. Se sustituyó por una cuadrícula acotada a Rastreo, campos con borde/foco y selector de fuentes. Altura posterior medida: 134,4 px.
- La regla compartida .button:disabled usaba cursor wait para cualquier bloqueo. Ahora solo aria-busy=true usa espera; disabled sin carga usa not-allowed. Se corrigió además el orden de props de Button: disabled=false ya no puede anular busy=true.
- El estilo global de record-list li imponía flex y comprimía el contenido de ejecuciones. El selector acotado .crawl .crawl-list > li preserva filas de ancho completo y contadores adaptables. No se rediseñaron módulos ajenos.
- La barra lateral se comprobó en ventana normal y al desplazar: sticky, top aproximadamente 0 y altura 900 px. No se confirmó un defecto de posición; la captura de página completa no representa por sí sola su posición durante scroll.
- El código servido en 5173 coincidió con Crawling.jsx local mediante el source map de Vite. No se detuvieron procesos.

### Comportamiento corregido

Los seis listados y los documentos comparten paginación. Con count <= page_size solo aparece el contador, sin Anterior/Siguiente. Con varias páginas se muestra Página N de M, se solicitan las páginas correspondientes y se deshabilitan los extremos. Mientras llega otra página aparece el mensaje de carga; no se representa como un botón de espera por inexistencia de otra página. Cambiar filtros remonta el listado en página 1.

La versión activa indica Versión seleccionada sin botón redundante. Otra versión solicita su ID global, renueva contenido/documentos y enfoca el encabezado al cargar; los fallos ofrecen reintento. El número visible sigue siendo numero, no id. Se conserva la selección por última observación exitosa, incluido A→B→A.

El detalle separa resumen, información extraída, advertencias, documentos e historial. Los contextos académicos repetidos se agrupan por URL/sección/función/contexto y reúnen sus expresiones originales. El contenido estructurado íntegro y texto técnico siguen accesibles en desplegables. No se cambian datos, cantidades, precisión temporal ni estado documental. Las notas manuales no se presentan como extracción automática. Pestañas activas y enlaces Abrir publicación / Ver detalle de ejecución tienen presentación explícita.

### Verificación de esta corrección

- Vitest: **50 aprobadas**, cero fallidas/omitidas (11,86 s). Incluye paginación de ida/vuelta en los seis recursos con filas sintéticas diferentes, límites, filtros a página 1, una página sin botones, ID global distinto del número, selección/error/reintento/foco y documentos, agrupación de contextos, Button ocupado y regresiones de navegación.
- Edge/Playwright: **3 aprobadas**, cero fallidas/omitidas. API simulada para interfaz: 1440, 390 y 320 px, campos con borde, formulario compacto, ausencia de desbordamiento, teclado, versiones, descarga adjunta/error/reintento, filtros, paginación y menú/cierre de sesión. El tercer caso recorre filtros y versiones a 1440 y 390 px. Un caso usa backend HTTP real y comprueba 403 anónimo en consulta y descarga.
- **18 consultas reales** de PostgreSQL y documentos con APIRequestFactory, autenticación inyectada en memoria y transacción READ ONLY. 200/no-store; huellas de **34 tablas iguales** antes/después. Metadatos: una fuente, dos publicaciones, dos ejecuciones; publicación 1 tiene una versión/observación; dos documentos por versión; seis accesos y dos incidencias por ejecución. Tamaño de página 12: los controles anteriores estaban correctamente deshabilitados por falta de otra página.
- Capturas adicionales de lista, detalle y ejecuciones a 1440/390 px con esas respuestas reales reproducidas localmente y una identidad visual sintética. No equivalen a una sesión real conectada. Revisadas junto a las capturas sintéticas; sin desbordamientos observados, contadores alineados y contenido legible. Evidencia local ignorada: outputs/rastreo/ui-*.png; no se modificó evidencia del rastreo.
- Django check: sin incidencias. ESLint y build: correctos, 64 módulos. No se modificó backend en esta corrección; no se repitieron ni se atribuyen como nuevas las nueve pruebas PostgreSQL de la etapa anterior. Ninguna prueba creó registros en desarrollo.
- Pendiente de revisión del usuario: recorrido con su sesión administradora real. No se usaron credenciales ni se modificaron cuentas para automatizarlo.

Comandos ejecutados, desde raíz salvo los npm indicados:

~~~powershell
.\.venv\Scripts\python.exe backend/manage.py check
$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
Set-Location frontend
npm.cmd test -- --run src/Crawling.test.jsx src/App.test.jsx src/PublicAccess.test.jsx
npm.cmd run test:e2e -- --config playwright.crawling.config.js
npm.cmd run lint
npm.cmd run build
~~~

Para revisar: abrir http://127.0.0.1:5173/gestion/rastreo, seleccionar SIAU, buscar Productivo, abrir publicación y comprobar Versión seleccionada. Desplegar evidencia completa y descargar un documento. Abrir Ejecuciones y Ver detalle de ejecución. Con los registros actuales se verá un contador simple; las páginas múltiples se probaron con datos sintéticos, sin ampliar la base real.

Confirmación posterior del usuario (28/10/2026): revisión manual de la bandeja y sus correcciones visuales completada; autorizado guardar esta implementación en commit local. Las limitaciones de las pruebas automatizadas anteriores se conservan como registro histórico.
