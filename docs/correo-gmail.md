# Avisos por correo

- La bandeja interna sigue siendo el registro principal. Al crear una notificación interna nueva, solo se prepara una entrega si la persona activó expresamente el correo, la beca es real y postulable, y la comparación de requisitos devuelve `cumple` en una opción. Las notificaciones anteriores no se envían retroactivamente.
- `CFG_PREFERENCIA_CORREO` guarda el consentimiento; ausencia de fila equivale a desactivado. `TRA_ENTREGA_CORREO` guarda una entrega por notificación interna, con estado, intentos y próximo intento. La clave única de `TRA_NOTIFICACION` ya identifica el evento por persona y convocatoria.
- La solicitud web nunca abre SMTP. El comando `enviar_correos_becas` revalida consentimiento, vigencia y compatibilidad antes de enviar. Solo reintenta fallos de conexión anteriores al envío, como máximo tres veces. Un resultado SMTP incierto queda `fallido` para revisión manual, sin reenvío automático.
- `notificaciones.0002` está aplicada en `becanexo_db`. `AVISOS_CORREO_HABILITADOS=True` está configurado localmente; el correo requiere consentimiento individual y una entrega nueva. Activar la bandera no reenvía avisos anteriores.

## Configuración local privada

En `backend/.env`, configurar `GMAIL_SMTP_USER` y `GMAIL_APP_PASSWORD` sin compartir ni versionar sus valores, además de `BECANEXO_PUBLIC_BASE_URL` con la URL que abrirán los destinatarios. El servidor es `smtp.gmail.com`, puerto 587 con TLS. Si faltan las dos credenciales, Django usa el backend de consola; el comando de entrega se niega a marcar mensajes de consola como enviados. La contraseña de aplicación de Google requiere verificación en dos pasos y puede no estar disponible para algunas cuentas institucionales.

## Primera prueba real, separada de la cola

Tras configurar Gmail SMTP y con autorización para enviar **un solo** correo a una dirección bajo control del administrador, ejecutar desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend/manage.py enviar_correos_becas --prueba-a DIRECCION_CONTROLADA --confirmar-prueba
```

Esta prueba envía un mensaje sintético, sin datos de postulantes ni convocatorias, y no cambia la base. La entrega operativa requiere consentimiento del destinatario y el comando `enviar_correos_becas --confirmar-envios` con un límite explícito; la tarea programada de correo permanece deshabilitada.

## Procesamiento local programado

La tarea Windows `BecaNexo-Notificaciones-Gmail` está registrada **deshabilitada**. Comprueba cada cinco minutos y al iniciar sesión (tras dos minutos). Usa la sesión interactiva del usuario, recupera una ejecución omitida y no inicia otra instancia si una sigue activa. Su acción llama a `scripts/correo-programado.ps1 -Ejecutar`, que usa el entorno virtual y `backend/.env` existentes. El script comprueba PostgreSQL, la base esperada, la bandera de avisos y SMTP; si no hay entregas vencidas, termina sin abrir Gmail. Procesa como máximo cinco por ejecución y registra únicamente estado y cantidades en `%LOCALAPPDATA%\BecaNexo\correo\programador.jsonl`.

Diagnóstico sin envíos:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File scripts/correo-programado.ps1 -Comprobar
Get-ScheduledTask -TaskName 'BecaNexo-Notificaciones-Gmail' | Select-Object TaskName,State
```

Antes de habilitar la tarea, esperar un evento real elegible, comprobar por lectura que la entrega pendiente pertenece exclusivamente a la cuenta administrada y ejecutar manualmente solo esa entrega:

```powershell
.\.venv\Scripts\python.exe backend/manage.py enviar_correos_becas --solo-id ID_ENTREGA --limite 1 --confirmar-envios
```

Comprobar después el estado `enviado` o el código de fallo en `TRA_ENTREGA_CORREO` y la recepción del mensaje. Este comando envía correo real; requiere autorización y no debe usarse con una entrega de otro destinatario. Los avisos internos antiguos no se encolan retroactivamente.

Activación posterior, solo tras esa prueba y autorización:

```powershell
Enable-ScheduledTask -TaskName 'BecaNexo-Notificaciones-Gmail'
Get-ScheduledTask -TaskName 'BecaNexo-Notificaciones-Gmail' | Select-Object TaskName,State
```

Para detenerla:

```powershell
Disable-ScheduledTask -TaskName 'BecaNexo-Notificaciones-Gmail'
```

Si la PC está apagada, no hay envíos; al volver e iniciar sesión se procesa una sola ventana, sin acumular disparos perdidos. Si PostgreSQL no responde, el script registra un fallo y no abre SMTP. Si no hay internet, el procesador aplica los reintentos limitados existentes para fallos de conexión; un resultado SMTP incierto queda retenido como fallido para revisión manual y no se reenvía solo. No registrar credenciales en la tarea ni en el archivo de resultados.

Verificación aislada del 17/11/2026: ocho pruebas nuevas de correo y tres regresiones de notificaciones internas aprobaron en `test_becanexo_fusion_db`; las cinco pruebas focalizadas de la pantalla de notificaciones, Django check, lint, build y `git diff --check` aprobaron.

Verificación de fase 2: se respaldó `becanexo_db` con dump legible y 42 documentos comprobados por SHA-256; se aplicó únicamente `notificaciones.0002`. `migrate --check`, Django check y `git diff --check` aprobaron. Antes y después permanecieron 14 usuarios, 20 convocatorias y 47 notificaciones internas. Las tablas de preferencias y entregas quedaron vacías. No se enviaron correos reales.
