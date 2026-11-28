# Recuperación de contraseña (postulantes)

Desde la v1.1 (27/11/2026), un postulante que olvidó su contraseña puede restablecerla desde el inicio de sesión mediante un enlace que llega al correo de su cuenta.

## Flujo

1. En `/login`, «¿Olvidaste tu contraseña?» lleva a `/recuperar-contrasena`.
2. La persona escribe su correo y el frontend llama a `POST /api/auth/recuperar-contrasena/` con `{"email"}`. La respuesta es **siempre** `200` con «Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la contraseña.». Es igual exista o no la cuenta, esté activa o no, y sea de postulante o de administración.
3. Solo si la cuenta existe, está activa y es de un postulante, se envía el correo «Restablece tu contraseña de BecaNexo». Contiene el enlace, su vigencia y «Si no fuiste tú, ignora este mensaje: tu contraseña no cambia».
4. El enlace abre `/restablecer-contrasena#uid=…&token=…`. La página lee uid y token del fragmento, los quita de la barra de direcciones y pide la contraseña nueva y su confirmación, mostrando los requisitos.
5. El frontend llama a `POST /api/auth/restablecer-contrasena/` con `{"uid", "token", "password", "password_confirm"}`. Si todo es válido, la contraseña cambia y se vuelve a `/login` con el aviso «Tu contraseña se actualizó…». No se inicia sesión automáticamente.
6. Errores posibles:

   | Caso | Respuesta | Qué ve la persona |
   |---|---|---|
   | Enlace inválido, vencido o ya usado | `400` con `codigo: "enlace_invalido"` | Pantalla «Enlace no válido», con acceso para pedir otro |
   | Contraseña débil | `400` con `password: […]` (validadores de Django) | El motivo, junto al campo |
   | Las dos contraseñas no coinciden | `400` con `password_confirm` | El aviso, junto al campo de confirmación |

## Seguridad

- **Token:** `default_token_generator` de Django (`PasswordResetTokenGenerator`), con el identificador de la cuenta codificado (`uid`).
  - No se guarda en la base y caduca a los `PASSWORD_RESET_TIMEOUT` segundos.
  - Depende del hash de la contraseña y del último inicio de sesión: deja de valer en cuanto la contraseña cambia (un solo uso) o la persona inicia sesión.
  - Un token de una cuenta de administración o inactiva se rechaza igual que uno alterado.
- **El enlace usa el fragmento (`#`):** uid y token no llegan a los registros del servidor ni a la cabecera Referer.
- **Nada se registra:** ni tokens, ni enlaces, ni correos solicitados. Un fallo de envío solo registra el tipo de error.
- **Sesiones previas:** el cambio usa `set_password()` sin `update_session_auth_hash`. Django guarda en cada sesión un hash derivado de la contraseña y lo comprueba en cada solicitud, así que **todas las sesiones abiertas de esa cuenta dejan de valer** al cambiarla.
- **Envío independiente:** el correo sale en un hilo aparte (`usuarios/recuperacion.py`), con `EMAIL_TIMEOUT` de 8 s y la misma configuración Gmail de los avisos.
  - La respuesta no espera a Gmail y no cambia si el envío falla. Así se evitan diferencias de tiempo evidentes entre cuentas existentes e inexistentes.
  - **No usa la cola de avisos** (`TRA_ENTREGA_CORREO`) ni la tarea programada, y no cuenta para el tope de avisos por destinatario.
- **CSRF:** las dos rutas son públicas, pero exigen CSRF como el resto de la autenticación.

## Límites (configurables; al superarlos responden `429`)

| Ruta | Límite | Variable |
|---|---|---|
| Solicitud, por IP | 20 por hora | `AUTH_RECUPERACION_IP_RATE` |
| Solicitud, por correo solicitado (normalizado, con HMAC; cuenta también correos inexistentes) | 5 por hora | `AUTH_RECUPERACION_CORREO_RATE` |
| Confirmación, por IP | 20 por hora | `AUTH_RESTABLECER_RATE` |

El mensaje de `429` no dice si el correo existe.

## Configuración

| Variable | Por defecto | Uso |
|---|---|---|
| `PASSWORD_RESET_TIMEOUT_MINUTOS` | 60 | Vigencia del enlace |
| `BECANEXO_PUBLIC_BASE_URL` | `http://127.0.0.1:5173` | URL del frontend con la que se construye el enlace; es la misma de los avisos por correo |
| `GMAIL_SMTP_USER`, `GMAIL_APP_PASSWORD` | — | Remitente; los mismos de los avisos |

Si las credenciales de Gmail no están configuradas, Django usa el backend de consola y el correo no llega a ningún sitio. La respuesta sigue siendo la misma.

## Cuentas de administración

No reciben enlace por este flujo: obtienen la misma respuesta genérica, sin envío. Su contraseña se cambia con el procedimiento administrativo que ya existe:

- `.\.venv\Scripts\python.exe backend/manage.py changepassword <correo>`;
- o el formulario de cambio de contraseña del administrador de Django.

## Limitaciones

- El límite de intentos usa la caché local en memoria del proceso. Con varios procesos o tras un reinicio se reinicia, como ocurre con los límites de registro e inicio de sesión.
- Si el correo no llega (Gmail caído o sin configurar), la persona no recibe ningún aviso del fallo, y es intencionado: la respuesta no puede variar. Solo queda una advertencia en el registro, sin datos personales.
- Iniciar sesión con la contraseña antigua mientras un enlace está pendiente lo invalida, porque el token depende del último inicio de sesión. En ese caso hay que pedir otro enlace.

## Archivos

- **Backend:**
  - `backend/usuarios/recuperacion.py` (token, enlace, mensaje y envío);
  - `backend/usuarios/api.py` (`RecuperarContrasenaView`, `RestablecerContrasenaView`);
  - `backend/usuarios/throttles.py`, `backend/usuarios/serializers.py` y `backend/usuarios/urls.py`;
  - la plantilla `backend/usuarios/templates/usuarios/restablecer_contrasena.txt` y `backend/config/settings.py`.
- **Frontend:** `frontend/src/pages/ForgotPassword.jsx`, `frontend/src/pages/ResetPassword.jsx`, `Login.jsx`, `App.jsx` y `api/client.js`.
- **Pruebas:** `backend/usuarios/test_recuperacion.py` y `frontend/src/PasswordReset.test.jsx`.
