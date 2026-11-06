# Ejecución local de BecaNexo

Estado actual: autenticación, perfiles, gestión administrativa de convocatorias, catálogo y favoritos. Ver api-favoritos.md para endpoints y recorrido de /favoritos. Con favoritos: 70 pruebas backend y 37 frontend aprobadas; recorrido nuevo de favoritos aprobado. Los tres recorridos anteriores corresponden a la etapa de convocatorias. Detalles y limitaciones en [avance.md](avance.md).

El catálogo público está en `/becas` y su detalle en `/becas/:id`. Los administradores acceden desde Inicio a `/gestion/convocatorias` y `/gestion/instituciones`; el backend comprueba el rol. La guía [api-convocatorias.md](api-convocatorias.md) contiene el flujo crear → publicar → consultar → editar → republicar.

`convocatorias.0001_initial` ya está aplicada en este entorno. El comando `cargar_catalogos_convocatorias` prepara idempotentemente dos tipos de beca y trece contratos; no crea ejemplos. El tercer recorrido E2E usa una única entidad y convocatoria DEMOSTRACIÓN con enlaces example.org y dos cuentas específicas sin contraseña utilizable. Las reutiliza sin duplicarlas y no modifica el superusuario. Consulta los detalles de esa fixture en la guía de convocatorias. Las capturas y servidores siguen el mismo manejo local descrito abajo.

Entorno comprobado: Windows, PowerShell, Python de `.venv`, PostgreSQL local y Node portable **24.22.1**. No es necesario modificar el PATH global. Usar siempre **127.0.0.1**, tanto para backend como para frontend.

## Terminal 1: backend

Desde la raíz del proyecto:

```powershell
Set-Location D:\Proyectos\BecaNexo
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

El backend lee las credenciales y demás configuración local desde `backend/.env`, que no se versiona. Se mantienen los valores existentes; no es necesario cambiar la contraseña de PostgreSQL ni el superusuario. Las migraciones de autenticación fueron aplicadas por el responsable y perfiles.0001_initial se aplicó en la etapa de perfil, tras verificar las pruebas. Estos comandos no ejecutan migraciones ni crean usuarios administradores.

El proxy de Vite conserva Host y Origin de `127.0.0.1:5173`, por lo que no hace falta añadir ese origen a `DJANGO_CSRF_TRUSTED_ORIGINS`. Django sigue exigiendo la cookie y `X-CSRFToken`. Solo si se usan orígenes distintos de forma deliberada se configura su lista explícita en `backend/.env`; no usar comodines. Abrir siempre el mismo host en el navegador: `localhost` y `127.0.0.1` no comparten cookies.

Para HTTP local, `SESSION_COOKIE_SECURE=False` y `CSRF_COOKIE_SECURE=False`; estos son los valores predeterminados. Mantener `DJANGO_ALLOWED_HOSTS` limitado a los hosts necesarios (incluido 127.0.0.1). No se requiere activar DEBUG para utilizar este frontend.

## Terminal 2: frontend

```powershell
Set-Location D:\Proyectos\BecaNexo
$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
node --version
npm.cmd --version
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

`node --version` debe mostrar v24.22.1 (el proyecto exige Node 24). `npm.cmd ci` instala exactamente el lockfile; solo es necesario tras clonar o cambiar dependencias, no en cada arranque. Usar npm.cmd evita la política de ejecución de npm.ps1. No instalar herramientas globales.

Abrir **http://127.0.0.1:5173/login**. También están disponibles `/registro` e `/inicio`; esta última requiere sesión. Los postulantes disponen de /perfil y /preferencias. `strictPort` impide que Vite cambie de puerto silenciosamente si 5173 está ocupado. Detener los servidores con Ctrl+C en sus respectivas terminales.

## Integración y datos

- Vite escucha en 127.0.0.1:5173 y reenvía `/api` a http://127.0.0.1:8000. Cambia Host para el destino, pero conserva Origin del navegador. No se configura CORS.
- El cliente usa fetch con rutas relativas y cookies same-origin. Solicita CSRF antes de registro/login y utiliza el token renovado devuelto por login; al recargar vuelve a obtener un token antes de una operación que lo necesite.
- El token CSRF se conserva únicamente en memoria. No se guardan contraseñas ni tokens en localStorage/sessionStorage. La cookie de sesión la gestiona el navegador y es HttpOnly.
- Registro crea un postulante y vuelve al login con confirmación. No crea perfil académico ni inicia sesión automáticamente.
- La aplicación consulta me al montar, espera el resultado y distingue 403/401 de errores de red/servidor. Ante un fallo de conexión ofrece reintentar sin asumir que el usuario cerró sesión. Las rutas del frontend no reemplazan permisos del servidor.
- Un 403 al enviar muestra un error y descarta el token en memoria; el siguiente intento solicita uno nuevo. No se reenvían automáticamente POST para evitar operaciones duplicadas. Un origen mal configurado requiere corregir la variable del backend.
- Un 429 muestra el tiempo Retry-After si existe. El contador sigue siendo local a cada proceso Django y no protege de forma distribuida.
- La página de inicio muestra nombre y rol reales. No hay datos ni API simulados en la aplicación, ni controles de funciones pendientes.

## Verificaciones automatizadas

Frontend, desde frontend/ con el PATH anterior:

```powershell
npm.cmd run lint
npm.cmd run build
npm.cmd test
```

Las pruebas Vitest/Testing Library simulan fetch exclusivamente dentro de `src/App.test.jsx`, `src/Profile.test.jsx` y `src/Offers.test.jsx`. Cubren registro, errores de campos y confirmación, prevención de envíos duplicados, restauración y espera de sesión, acceso anónimo, fallo de red y de servidor en me, reintento, logout/204, renovación CSRF y errores 403/429/500. No escriben en PostgreSQL. La compilación produce `frontend/dist/`, excluido de Git; no es un despliegue de producción.

Backend, desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios perfiles convocatorias favoritos --keepdb --verbosity 2
```

Estas pruebas usan exclusivamente test_becanexo_db, sin paralelismo. La nueva prueba de origen Vite confirma tanto la aceptación de su origen con token como el rechazo sin token.

### Navegador con backend real

Con los puertos 8000 y 5173 libres (detener primero las terminales anteriores), desde frontend/ y con Node 24 en PATH:

```powershell
npm.cmd run test:e2e
```

Requiere Microsoft Edge instalado. Playwright utiliza el Edge local sin ventana, arranca y detiene sus propios servidores, y proporciona el origen CSRF solo al proceso Django. No reutiliza servidores existentes. El flujo completo usa la base de desarrollo configurada en `.env`, **no una API simulada**: crea una cuenta desechable `e2e-<UUID>@example.com` con contraseña aleatoria y nombre «Verificación desechable». El segundo recorrido crea otra cuenta y su perfil; elimina solo la experiencia creada durante ese recorrido. Ambas cuentas y los otros datos de prueba permanecen en desarrollo. No usar este comando apuntando a producción. No consulta ni modifica el superusuario existente.

El recorrido comprueba registro 201 sin sesión automática, login 200 con correo en mayúsculas y Origin real, restauración tras recargar, datos de usuario, logout 204, acceso anónimo posterior y ausencia de almacenamiento web. Captura las pantallas vacías de login/registro y el inicio con nombre desechable a 1440×1000 y 390×844. Las capturas y resultados quedan en `frontend/test-results/`, excluido de Git; no se graban trazas ni videos con credenciales.

## Referencia visual y límites

Se visualizaron las páginas 3 y 4 del PDF `docs/diseno/BecaNexo_Interfaces_y_ER_v05.pdf`: panel azul #17345C, acciones #2563EB, fondo #F5F7FB, texto #17243B, tipografía Inter, formularios y distribución. Inter se sirve desde el paquete local @fontsource/inter, sin peticiones a Google Fonts.

Se adaptó el botón de entrada para ambos roles y se omitieron enlaces de navegación simulada, acceso administrativo separado, aviso de privacidad no implementado y promesas de funciones pendientes. El texto secundario y pie identifican el avance real. En móvil el panel se apila sobre el formulario. Perfil y preferencias ya están implementados. El catálogo y la gestión administrativa también están implementados. No se implementaron IA, rastreo ni recuperación de contraseña.

La verificación visual se hizo en Edge a esos dos tamaños; no sustituye una auditoría de accesibilidad completa ni pruebas en todos los navegadores/dispositivos. Antes de desplegar siguen pendientes HTTPS, cookies Secure, el enrutamiento SPA del servidor y la estrategia de límites compartidos. No se publicó el sitio.


## Preparación y comprobación del perfil

En este entorno `perfiles.0001_initial` ya está aplicada y los catálogos están cargados. Para comprobarlo o preparar otra instalación, desde la raíz y verificando primero el destino configurado:

```powershell
.\.venv\Scripts\python.exe backend\manage.py showmigrations perfiles
.\.venv\Scripts\python.exe backend\manage.py migrate --plan
# Solo si corresponde aplicar las migraciones pendientes en ese entorno:
.\.venv\Scripts\python.exe backend\manage.py migrate --noinput
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos
```

La carga es idempotente y no elimina registros. Los catálogos iniciales contienen 249 países/territorios, 12 idiomas y 11 áreas. Las fuentes están en `backend/perfiles/data/FUENTES.md`. Antes de ejecutar pruebas backend, comprobar que TEST.NAME sea `test_becanexo_db`, distinto de `becanexo_db`; mantener `--keepdb` y no añadir `--parallel`.

El recorrido manual reproducible y las reglas están en [api-perfil.md](api-perfil.md). Los recorridos E2E requieren estas migraciones y catálogos en desarrollo. Al finalizar perfiles se obtuvieron 46 pruebas backend, 22 frontend y 2 recorridos aprobados; los resultados actuales constan en avance.md. Las capturas de perfil y preferencias también están en `frontend/test-results/` y no se versionan.
