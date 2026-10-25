# Avance de BecaNexo

## Estado actual — perfil y preferencias (25 de octubre de 2026)

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
