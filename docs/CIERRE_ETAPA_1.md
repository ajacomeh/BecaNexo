# Cierre de etapa 1: rastreo y revisión administrativa

Fecha: 29/10/2026. Estado del hito: **completado y validado**. Este cierre se limita al rastreo y revisión administrativa actuales; no declara terminada toda BecaNexo. No inicia la etapa 2 de análisis de arquitectura ni una limpieza del repositorio.

## Objetivo y alcance

Conservar evidencia pública de SIAU con trazabilidad y permitir su consulta y revisión por administradores, separando extracción, documentación, admisibilidad del oferente, vigencia y publicación. La validación final conserva todos los datos de desarrollo; no crea decisiones editoriales, convocatorias ni nuevas descargas.

## Funciones implementadas

- Extracción pública conservadora: expresiones y contextos académicos, formación previa, evidencia original, advertencias y temporización de peticiones; no convierte automáticamente menciones en opciones/requisitos confirmados.
- Fuente configurada y activada con auditoría; ejecuciones manuales persistidas, exclusión concurrente, recuperación controlada e idempotencia. Publicación automática bloqueada.
- Archivo privado HTML/PDF, huellas, accesos e incidencias; identidades por fuente/URL, versiones inmutables, documentos exactos y observaciones. A→B→A conserva la secuencia de observaciones sin duplicar versiones.
- Bandeja administrativa: publicaciones, filtros/paginación, detalles, versiones, evidencia, ejecuciones/accesos/incidencias y descarga protegida como adjunto. Las descargas no equivalen a aprobación.
- Revisión de extracción, documentación y oferente en AUD_REVISION_RASTREO: versión exacta, documento cuando corresponde, administrador de la sesión, fecha del servidor y justificación. Historial inmutable, rectificación mediante nueva fila, clave de acción para reintentos y conflicto 409 ante decisiones concurrentes obsoletas. No hay aprobación heredada entre evidencias.
- Formulario accesible con identificación del destino, decisiones vigentes e historial, carga, cancelación, confirmación y errores conservando el texto. Ausencia de decisiones se muestra pendiente sin inventar registros.

## Tecnologías y módulos

Django 5.2, Django REST Framework, autenticación nativa por sesiones/CSRF y PostgreSQL local. Aplicaciones rastreo, usuarios y adaptador SIAU en convocatorias; React, Vite, Tailwind/estilos locales e iconografía Lucide existente. Verificación con Django Test Runner, Vitest/Testing Library y Playwright/Edge, usando Node 24. No se añadieron dependencias durante el cierre.

## Modelo y migraciones

Rastreo 0001–0007 aplicadas en desarrollo y pruebas. En este hito editorial se añadieron:

- **0006_revision_editorial:** version_id y evidencia_id opcionales en AUD_REVISION_RASTREO, ampliación de CHECK de objeto y restricciones/índices de decisiones y sustitución.
- **0007_integridad_revision_editorial:** pertenencia documental, autor válido, sustitución coherente y bloqueo de aprobación de convenios; conserva los triggers anteriores de inmutabilidad.

Ambas se aplicaron en la etapa anterior después de pruebas y respaldo; **no se aplicaron nuevas migraciones durante este cierre**. showmigrations confirma X; migrate --plan no tiene operaciones; makemigrations --check --dry-run no detecta cambios. Sin tablas duplicadas de auditoría ni modificaciones de catálogo. [Suplemento efectivo](Modelo/Revision_administrativa_rastreo.md); v0.6 histórico conservado.

## Pruebas finales ejecutadas

| Verificación | Resultado final | Entorno |
| --- | --- | --- |
| Django: rastreo, usuarios y convocatorias.test_siau | **116 aprobadas**, 0 fallidas, 0 omitidas; 106,253 s; salida 0 | test_becanexo_db, suite secuencial, documentos temporales y red SIAU simulada |
| Vitest: todos los archivos disponibles | **110 aprobadas**, 13 archivos, 0 fallidas/omitidas; 49,85 s; salida 0 | jsdom y APIs simuladas |
| Playwright: revisión administrativa | **3 aprobadas**, 0 fallidas/omitidas; 8,7 s; salida 0 | Edge a 1440, 390 y 320 px, API/sesión simuladas |
| Navegador anónimo de integración | Login exigido, cinco GET administrativos 403, cero errores JavaScript; salida 0 | Vite y Django reales, sin interceptores |
| ESLint / build de producción | Correctos, salida 0 | Node 24, build 2005 módulos |
| Django check / comprobación de migraciones | Sin incidencias / sin cambios ni operaciones pendientes | Configuración real |

Los casos backend cubren validaciones de extracción/documentación/oferente, actor y campos rechazados, autenticación/CSRF/permisos, historial inmutable, rectificaciones, reintentos, concurrencia entre administradores, versiones históricas y ausencia de herencia. Incluyen persistencia, acceso seguro y regresiones del extractor. La suite no usa --parallel; únicamente pruebas específicas abren conexiones concurrentes a la base de pruebas.

### Aislamiento de escrituras

Antes de ejecutar se comprobó NAME=becanexo_db, TEST.NAME=test_becanexo_db, nombres distintos y ausencia de TEST.MIRROR. Django Test Runner configura la base de pruebas antes de ejecutar casos. El setup común de rastreo comprueba el nombre **antes de crear usuarios** y usa TemporaryDirectory/override_settings para documentos; los tests editoriales reutilizan ese setup. AppConfig no ejecuta consultas ni escrituras al importar. No se ejecutan comandos de demostración ni el bootstrap de otros recorridos e2e.

Las pruebas de guardado/rectificación/concurrencia usan PostgreSQL de pruebas; las escrituras del navegador se interceptan solo en su contexto de pruebas. No se inyecta la simulación en la aplicación normal. No se escriben revisiones de desarrollo para demostrar funciones.

Comandos finales, desde raíz salvo npm desde frontend:

```powershell
.\.venv\Scripts\python.exe backend/manage.py test rastreo usuarios convocatorias.test_siau --keepdb --verbosity 1
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend/manage.py showmigrations rastreo
.\.venv\Scripts\python.exe backend/manage.py migrate --plan
$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
Set-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e -- --config playwright.reviews.config.js
```

## Integración real y validación manual

Se reutilizó http://127.0.0.1:5173, con proxy /api hacia Django en 127.0.0.1:8000. La etapa previa comprobó que los módulos servidos coincidían con los archivos locales. setup.js pertenece a Vitest, no al arranque normal. Durante el cierre se verificó nuevamente la integración HTTP anónima, sin API simulada, con redirección al login y rechazo 403. Los ejecutores finalizaron con salida 0; no se detuvieron servidores ajenos.

Se repitieron **14 GET administrativos reales** con APIRequestFactory, autenticación inyectada en memoria y transacción READ ONLY: fuentes, publicaciones, ambos detalles, versiones, observaciones, documentos y revisiones, todos 200/no-store. **42 GET rechazados 403** para anónimos, postulantes e inactivos (los roles de prueba se representaron en memoria, sin guardar cuentas). No se confunde esta verificación con una sesión administrativa real de navegador.

**Validación manual del usuario, confirmada expresamente al solicitar el cierre:** acceso administrativo correcto; las dos publicaciones, detalles, versiones y documentos correctos; apertura y cancelación del formulario correctas; ningún error visual o funcional; **no guardó decisiones reales**. Esta validación completa el recorrido autenticado que las comprobaciones anónimas/inyección en memoria no acreditaban.

## Datos, integridad y respaldo

Se conservan dos publicaciones, dos versiones, cuatro relaciones documentales, dos observaciones y dos ejecuciones; dos revisiones históricas de configuración y **cero revisiones editoriales**. No hay vínculos canónicos ni publicación automática. No se modificaron cuentas, perfiles, favoritos o demostraciones.

Huellas de **34 tablas** iguales antes/después de las consultas; comparación adicional de las columnas preexistentes de **32 tablas principales** contra las huellas anteriores a 0006/0007, sin diferencias. Restricciones PostgreSQL validadas y triggers de revisión/inmutabilidad activos. La diferencia 34/32 corresponde a incluir relaciones auxiliares en la primera comprobación.

Respaldo existente verificado, sin crear otro:

`D:\Respaldos_BecaNexo\becanexo_pre_revisiones_20261029T103140Z_bd8aa7ea`

Dump custom de 210545 bytes, documentos, manifiesto y listado. SHA-256 del dump y tamaño/huellas de los **nueve archivos** correctos; pg_restore --list salida 0. **No se realizó restauración completa**, ni se afirma que el listado la sustituya. Procedimiento reproducible en [respaldo-rastreo.md](respaldo-rastreo.md).

## Archivos del commit y referencia

Cambios del hito conservados y revisados, sin reorganización:

- backend/rastreo: api.py, models.py, urls.py, revisiones.py, test_revisiones.py y migraciones 0006/0007.
- frontend: pages/Crawling.jsx y Crawling.css, components/CrawlingReviews.jsx, CrawlingReviews.test.jsx, e2e/reviews.spec.js y playwright.reviews.config.js.
- docs: avance.md, este cierre, consulta-administrativa-rastreo.md, decisiones-recomendacion-rastreo.md, propuesta-persistencia-rastreo.md, respaldo-rastreo.md, Modelo/Diccionario.md y Modelo/Revision_administrativa_rastreo.md.

Excluidos .env, .venv, node_modules, dist, test-results, outputs/rastreo, credenciales y respaldos. No se identificaron cambios de contenido ajenos al hito para incluir. Modelo_ER.mmd no presenta diferencia de contenido y no forma parte de esta selección. Logs y scripts operativos locales permanecen ignorados; no se borran.

Commit local de cierre: **feat(rastreo): cerrar revision administrativa y validacion integral**. Su referencia permanente es el commit que incorpora este documento; obtener el identificador exacto con:

```powershell
git log --diff-filter=A --format="%H %s" -- docs/CIERRE_ETAPA_1.md
git status --short
```

La entrega final informa el hash y el estado posterior al commit. No se hace push ni despliegue.

## Límites y continuidad

No quedan errores críticos detectados para este hito. La revisión sustantiva de SIAU debe realizarla un administrador tras examinar la evidencia; no está aprobada por esta validación técnica. Guardar una revisión real modifica el historial. No se ensayó restauración completa del respaldo.

Siguen fuera de alcance: evidencia estructurada de convenios y su aprobación, propuestas de cambio, vinculación/creación/publicación de convocatorias desde rastreo, publicación automática, nuevas fuentes, programación diaria, IA/afinidad y notificaciones. No se altera la semántica pendiente de fechas/topes/equivalencias.

El hito queda preparado para comenzar posteriormente la **etapa 2: análisis y comprensión de la arquitectura del código**. No se ejecuta ninguna tarea de esa etapa ni limpieza general como parte de este cierre.
