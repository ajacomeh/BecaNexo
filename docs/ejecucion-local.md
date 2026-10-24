# Ejecución local de BecaNexo

Entorno comprobado: Windows, PowerShell, Python de `.venv`, PostgreSQL local y Node portable **24.22.1**. No es necesario modificar el PATH global. Usar siempre **127.0.0.1**, tanto para backend como para frontend.

## Terminal 1: backend

Desde la raíz del proyecto:

```powershell
Set-Location D:\Proyectos\BecaNexo
$env:DJANGO_CSRF_TRUSTED_ORIGINS = 'http://127.0.0.1:5173'
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

El backend lee las credenciales y demás configuración local desde `backend/.env`, que no se versiona. Se mantienen los valores existentes; no es necesario cambiar la contraseña de PostgreSQL ni el superusuario. Las migraciones de desarrollo ya fueron aplicadas por el responsable. Estos comandos no ejecutan migraciones ni crean usuarios administradores.

La variable de origen puede añadirse al `.env` local en lugar de declararla en el proceso; su valor no es secreto y está documentado en `backend/.env.example`. Sin ella, una petición POST desde Vite será rechazada por CSRF aunque contenga token. Por defecto la lista de orígenes confiables está vacía. No usar comodines.

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

Abrir **http://127.0.0.1:5173/login**. También están disponibles `/registro` e `/inicio`; esta última requiere sesión. `strictPort` impide que Vite cambie de puerto silenciosamente si 5173 está ocupado. Detener los servidores con Ctrl+C en sus respectivas terminales.

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

Las pruebas Vitest/Testing Library simulan fetch exclusivamente dentro de `src/App.test.jsx`. Cubren registro, errores de campos y confirmación, prevención de envíos duplicados, restauración y espera de sesión, acceso anónimo, fallo de red y de servidor en me, reintento, logout/204, renovación CSRF y errores 403/429/500. No escriben en PostgreSQL. La compilación produce `frontend/dist/`, excluido de Git; no es un despliegue de producción.

Backend, desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios --keepdb --verbosity 2
```

Estas pruebas usan exclusivamente test_becanexo_db, sin paralelismo. La nueva prueba de origen Vite confirma tanto la aceptación de su origen con token como el rechazo sin token.

### Navegador con backend real

Con los puertos 8000 y 5173 libres (detener primero las terminales anteriores), desde frontend/ y con Node 24 en PATH:

```powershell
npm.cmd run test:e2e
```

Requiere Microsoft Edge instalado. Playwright utiliza el Edge local sin ventana, arranca y detiene sus propios servidores, y proporciona el origen CSRF solo al proceso Django. No reutiliza servidores existentes. El flujo completo usa la base de desarrollo configurada en `.env`, **no una API simulada**: crea una cuenta desechable `e2e-<UUID>@example.com` con contraseña aleatoria y nombre «Verificación desechable». Cada ejecución deja esa cuenta en desarrollo y no elimina registros. No usar este comando apuntando a producción. No consulta ni modifica el superusuario existente.

El recorrido comprueba registro 201 sin sesión automática, login 200 con correo en mayúsculas y Origin real, restauración tras recargar, datos de usuario, logout 204, acceso anónimo posterior y ausencia de almacenamiento web. Captura las pantallas vacías de login/registro y el inicio con nombre desechable a 1440×1000 y 390×844. Las capturas y resultados quedan en `frontend/test-results/`, excluido de Git; no se graban trazas ni videos con credenciales.

## Referencia visual y límites

Se visualizaron las páginas 3 y 4 del PDF `docs/diseno/BecaNexo_Interfaces_y_ER_v05.pdf`: panel azul #17345C, acciones #2563EB, fondo #F5F7FB, texto #17243B, tipografía Inter, formularios y distribución. Inter se sirve desde el paquete local @fontsource/inter, sin peticiones a Google Fonts.

Se adaptó el botón de entrada para ambos roles y se omitieron enlaces de navegación simulada, acceso administrativo separado, aviso de privacidad no implementado y promesas de funciones pendientes. El texto secundario y pie identifican el avance real. En móvil el panel se apila sobre el formulario. No se implementaron perfil académico, catálogo, IA, rastreo ni recuperación de contraseña.

La verificación visual se hizo en Edge a esos dos tamaños; no sustituye una auditoría de accesibilidad completa ni pruebas en todos los navegadores/dispositivos. Antes de desplegar siguen pendientes HTTPS, cookies Secure, el enrutamiento SPA del servidor y la estrategia de límites compartidos. No se publicó el sitio.
