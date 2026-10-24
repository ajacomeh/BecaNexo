# API de autenticación por sesiones

Implementada el 24 de octubre de 2026 con Django REST Framework. Prefijo `/api/auth/`, cuerpos JSON y respuestas JSON salvo logout (sin cuerpo). Se utilizan las sesiones nativas de Django; no JWT ni almacenamiento de credenciales en localStorage.

## Contrato

`usuario` contiene exclusivamente `id`, `email`, `nombre`, `rol`.

| Método y ruta | Entrada | Éxito | Errores específicos |
|---|---|---|---|
| GET csrf/ | Ninguna | 200: `{"csrfToken": "..."}` y cookie csrftoken | — |
| POST registro/ | nombre, email, password, password_confirm | 201: objeto usuario; no inicia sesión | 400: campos inválidos, adicionales, contraseña débil, confirmación incorrecta o duplicado; 429: límite |
| POST login/ | email, password | 200: `{"usuario": {...}, "csrfToken": "..."}` y cookie sessionid | 400: entrada inválida o credenciales rechazadas; 429: límite |
| GET me/ | Cookie de sesión | 200: objeto usuario | 403: sin sesión válida |
| POST logout/ | Cookie de sesión; cuerpo vacío o `{}` | 204: sin cuerpo; sesión invalidada | 403: sin sesión válida |

Todos los POST requieren cookie CSRF y encabezado `X-CSRFToken`; ausencia, token inválido u origen no autorizado producen 403. La comprobación ocurre antes del procesamiento de datos y también para anónimos. En DRF, SessionAuthentication por sí sola omite CSRF para anónimos; la clase CSRFSesionAuthentication lo exige explícitamente con el mecanismo de verificación de Django.

Los métodos no admitidos producen 405 una vez superadas autenticación/CSRF; OPTIONS está habilitado como metadatos de DRF. No se habilitó HEAD. JSON mal formado produce 400; un cuerpo con tipo de contenido no admitido produce 415. DRF puede devolver 406 si Accept no permite JSON. Los errores de validación usan claves de campo/listas o `detail`; nunca se devuelve el valor de la contraseña ni el hash.

Login devuelve el mismo 400 y `{"detail": "Correo o contraseña incorrectos."}` para correo inexistente, contraseña incorrecta o cuenta inactiva. Un cuerpo incompleto tiene errores de validación, no una respuesta de autenticación. El correo se normaliza según la política del manager: quitar espacios exteriores y pasar a minúsculas.

Registro rechaza todo campo fuera de los cuatro permitidos, incluidos rol y privilegios. Usa create_user con sus valores predeterminados de postulante activo sin privilegios. No crea perfil académico. La unicidad se resuelve en PostgreSQL, dentro de una transacción: un conflicto único se captura fuera del bloque atómico y devuelve 400, también si dos solicitudes compiten por el mismo correo. No se depende de una preconsulta de existencia. Otros errores de integridad no se ocultan como duplicados.

## Flujo CSRF y sesiones

1. Obtener GET csrf/ y conservar cookies. El token de la respuesta puede mantenerse en memoria para X-CSRFToken.
2. Registrar con el token si corresponde. Después del registro sigue siendo necesario iniciar sesión.
3. Enviar POST login/ con token y cookies. Django rota el secreto CSRF y gestiona la sesión. Reemplazar el token en memoria por csrfToken de esta respuesta. También puede obtenerse uno válido con un nuevo GET csrf/.
4. Consultar GET me/ enviando la cookie de sesión.
5. Enviar POST logout/ con el token actualizado. Una cookie de sesión antigua ya no permite consultar me/ después de cerrar sesión.

Todas las respuestas de estas vistas, incluidos errores, llevan Cache-Control con `private`, `no-store`, `no-cache`, `max-age=0` y `must-revalidate`. No registrar cuerpos de credenciales, cookies o tokens en aplicaciones, proxies o herramientas de diagnóstico.

## Cookies y límites locales

La cookie de sesión es HttpOnly y SameSite=Lax. SESSION_COOKIE_SECURE y CSRF_COOKIE_SECURE se leen del entorno y valen False por defecto para HTTP local en 127.0.0.1; ambas deben configurarse True bajo HTTPS. No se habilitó CORS. Para el frontend local, Vite utiliza proxy /api y conserva Origin: configurar DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173 en el proceso del backend o su .env. La lista queda vacía si se omite la variable; confiar en un origen no elimina la obligación del token CSRF. Véase ejecucion-local.md. HttpOnly no sustituye la prevención de XSS; HTTPS es necesario fuera del entorno local.

Los límites configurables son AUTH_REGISTRO_RATE=`5/hour` y AUTH_LOGIN_RATE=`10/minute`. Se cuentan solicitudes que alcanzan el throttle, incluidas entradas inválidas y éxitos; un rechazo previo por CSRF no consume este contador. Se usan scopes separados por operación y REMOTE_ADDR. X-Forwarded-For se ignora. Las claves son `throttle_<scope>_<HMAC de REMOTE_ADDR>`, con salted_hmac de Django, y almacenan una lista temporal de marcas de tiempo, sin correos ni contraseñas. El 429 incluye Retry-After.

El alias de caché `auth_throttle` utiliza LocMemCache, ubicación `becanexo-auth-throttle`. Solo cubre el proceso local, se pierde al reiniciar y no comparte contadores entre procesos. SimpleRateThrottle no garantiza conteos estrictos bajo concurrencia: no es una protección distribuida ni garantía frente a ataques. Usuarios detrás de NAT comparten límite; detrás de un proxy se limitaría su IP hasta diseñar una política confiable. No se incorporaron Redis ni servicios adicionales.

## Comprobación reproducible

Desde la raíz, iniciar el servidor local sin cambiar DEBUG ni credenciales:

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

En otra terminal PowerShell, usar una cuenta de pruebas local ya registrada. Este flujo inicia y cierra su sesión; no modifica su contraseña. No compartir ni imprimir las variables que contienen cookies o tokens.

```powershell
$base = 'http://127.0.0.1:8000/api/auth'
$csrf = Invoke-RestMethod "$base/csrf/" -SessionVariable navegador
$correo = Read-Host 'Correo'
$claveSegura = Read-Host 'Contraseña' -AsSecureString
$credencial = [System.Net.NetworkCredential]::new('', $claveSegura)
$cuerpo = @{email=$correo; password=$credencial.Password} | ConvertTo-Json
$entrada = Invoke-RestMethod "$base/login/" -Method Post -WebSession $navegador -ContentType 'application/json' -Headers @{'X-CSRFToken'=$csrf.csrfToken} -Body $cuerpo
$yo = Invoke-RestMethod "$base/me/" -WebSession $navegador
$salida = Invoke-WebRequest "$base/logout/" -UseBasicParsing -Method Post -WebSession $navegador -ContentType 'application/json' -Headers @{'X-CSRFToken'=$entrada.csrfToken} -Body '{}'
$salida.StatusCode # 204
try { Invoke-RestMethod "$base/me/" -WebSession $navegador | Out-Null } catch { [int]$_.Exception.Response.StatusCode } # 403
Remove-Variable cuerpo,credencial,claveSegura,entrada,csrf,navegador
```

Para comprobar registro, enviar antes del login un POST registro/ con los cuatro campos permitidos, cookie y token de csrf/; usar un correo nuevo. Esto crea una cuenta en la base del servidor. Para verificar sin crear datos de desarrollo, preferir la suite automatizada:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios --keepdb --verbosity 2
```

La suite usa test_becanexo_db, sin paralelismo. AuthAPITests usa APIClient(enforce_csrf_checks=True) y limpia solo el alias de caché de límites antes y después de cada prueba. Las pruebas de 429 reducen temporalmente las tasas. Se prueba la captura de un conflicto único real de PostgreSQL; no es una prueba de carga ni una simulación de tráfico concurrente.
