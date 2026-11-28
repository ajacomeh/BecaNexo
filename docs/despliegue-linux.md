# Despliegue en Linux: compatibilidad y ajustes de producción

Desde la v1.1 (27/11/2026), BecaNexo puede arrancar en un servidor Linux. **En Windows y en local nada cambia:** cada ajuste nuevo se controla con una variable de entorno cuyo valor por defecto deja el comportamiento de siempre. El `.env` de desarrollo, el runserver y las tareas programadas (`BecaNexo-Rastreo-SIAU` y `BecaNexo-Notificaciones-Gmail`) siguen igual.

El empaquetado (Docker, servidor WSGI y servicio de estáticos) queda para un paso posterior. Las cifras de memoria y el tamaño de servidor recomendado están en `D:\Documentacion_BecaNexo\medicion_despliegue_20261127.md`.

## Qué se cambió y por qué

| Archivo | Antes | Ahora |
|---|---|---|
| `backend/rastreo/web_launch.py` | `import msvcrt` en la cabecera. Este módulo, que sostiene el botón «Iniciar rastreo», lo importan `rastreo/api_control.py` y, con él, las URL: en Linux no cargaba ninguna URL. | `msvcrt` solo si existe. En Windows, el mismo bloqueo (`msvcrt.locking`) y el mismo proceso separado sin consola. En Linux, `fcntl.flock` (no bloqueante) y `start_new_session=True`. |
| `backend/rastreo/api_control.py` | El botón siempre intenta lanzar el rastreo. | Con `RASTREO_WEB_LANZAMIENTO_HABILITADO=False`, el POST responde `409` con «El rastreo desde la web está desactivado en este entorno.» y el GET indica `puede_iniciar: false`. Por defecto, la respuesta de siempre. |
| `backend/scripts/download_semantic_model.py` | Comprobaba AVX2 con `ctypes.windll`, que solo existe en Windows. | `tiene_avx2()`: en Windows, la misma API; en Linux, los indicadores de `/proc/cpuinfo`. Si falta AVX2, falla con una explicación; si no se puede determinar, avisa y continúa. La verificación SHA-256 del modelo no cambia. |
| `backend/config/settings.py` | Sin `STATIC_ROOT`, HSTS, redirección a HTTPS ni cabecera de proxy. | Todos estos ajustes se activan solo por variable (lista abajo). |
| `backend/usuarios/throttles.py` | Los límites de intentos usaban siempre `REMOTE_ADDR`. Detrás de un proxy, todos los clientes compartían la IP del proxy. | Con `DJANGO_NUM_PROXIES`, se usa la IP real del cliente según `X-Forwarded-For`, a través de DRF. Sin la variable, como siempre: `X-Forwarded-For` se ignora, porque el cliente puede falsificarlo. |

## Variables de entorno

Solo nombres y significado; nunca se versionan valores reales.

**Nuevas** (por defecto, el comportamiento actual):

| Variable | Por defecto | Significado |
|---|---|---|
| `DJANGO_BEHIND_PROXY` | `False` | Con `True`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`: Django confía en el proxy para saber que la petición llegó por HTTPS. Activar solo si el proxy fija esa cabecera. |
| `DJANGO_SECURE_SSL_REDIRECT` | `False` | Redirigir HTTP a HTTPS (`SECURE_SSL_REDIRECT`). |
| `DJANGO_SECURE_HSTS_SECONDS` | `0` | Duración de HSTS en segundos. Conviene empezar con un valor corto. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | HSTS también para los subdominios. |
| `DJANGO_SECURE_HSTS_PRELOAD` | `False` | Marca de precarga HSTS. |
| `DJANGO_STATIC_ROOT` | sin definir | Carpeta de destino de `collectstatic` (estáticos del admin de Django). |
| `DJANGO_NUM_PROXIES` | sin definir | Número de proxies de confianza delante de Django, para los límites de intentos. |
| `RASTREO_WEB_LANZAMIENTO_HABILITADO` | `True` | `False` desactiva «Iniciar rastreo» desde el panel (demo en la nube). |

**Ya existentes, necesarias en producción:**

| Variable | Significado |
|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django. |
| `DJANGO_ALLOWED_HOSTS` | Dominios del servidor. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión a PostgreSQL. |
| `BECANEXO_PUBLIC_BASE_URL` | URL pública HTTPS del frontend, usada en los enlaces de los correos. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origen HTTPS del sitio. |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` con HTTPS. |
| `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD` | Opcionales: correo de recuperación de contraseña. |
| `SEMANTIC_MODEL_DIR` | Carpeta del modelo local, si no está en la ruta por defecto. |

Con `DJANGO_DEBUG=False` y las variables de cookies, HSTS y redirección activadas, `manage.py check --deploy` ya no muestra `security.W004` ni `W008`. Quedan `W005` (HSTS para subdominios) y `W021` (precarga), que se activan a propósito solo si se quieren.

## Limitaciones conocidas

- **Límites de intentos:** su caché vive en la memoria de cada proceso. Con 2 procesos el límite efectivo se duplica, y se reinicia con cada reinicio. Es aceptable para el demo.
- **`DJANGO_NUM_PROXIES`:** debe coincidir con los proxies reales. Si es mayor, el cliente podría elegir su IP con `X-Forwarded-For`.
- **Rastreo y avisos en Linux:** el lanzamiento desde la web funciona, pero el rastreo y las tareas programadas siguen pensados para el equipo Windows del proyecto. En el demo conviene `RASTREO_WEB_LANZAMIENTO_HABILITADO=False` y `AVISOS_CORREO_HABILITADOS=False`.
- **Modelo:** está cuantizado para x86-64 con AVX2. Un servidor ARM no es el destino previsto.
- **Pendiente para el paso siguiente:** el servidor WSGI y el servicio de estáticos (no hay dependencias nuevas en `requirements.txt`).
