# Avisos por correo

- La bandeja interna sigue siendo el registro principal. Al crear una notificación interna nueva, solo se prepara una entrega si la persona activó expresamente el correo, la beca es real y postulable, y la comparación de requisitos devuelve `cumple` en una opción. Las notificaciones anteriores no se envían retroactivamente.
- `CFG_PREFERENCIA_CORREO` guarda el consentimiento; ausencia de fila equivale a desactivado. `TRA_ENTREGA_CORREO` guarda una entrega por notificación interna, con estado, intentos y próximo intento. La clave única de `TRA_NOTIFICACION` ya identifica el evento por persona y convocatoria.
- La solicitud web nunca abre SMTP. El comando `enviar_correos_becas` revalida consentimiento, vigencia y compatibilidad antes de enviar. Solo reintenta fallos de conexión anteriores al envío, como máximo tres veces. Un resultado SMTP incierto queda `fallido` para revisión manual, sin reenvío automático.
- `notificaciones.0002` está aplicada en `becanexo_db`. `AVISOS_CORREO_HABILITADOS` permanece en `False`; habilitar los avisos operativos requiere una autorización posterior y consentimiento individual.

## Configuración local privada

En `backend/.env`, configurar `GMAIL_SMTP_USER` y `GMAIL_APP_PASSWORD` sin compartir ni versionar sus valores, además de `BECANEXO_PUBLIC_BASE_URL` con la URL que abrirán los destinatarios. El servidor es `smtp.gmail.com`, puerto 587 con TLS. Si faltan las dos credenciales, Django usa el backend de consola; el comando de entrega se niega a marcar mensajes de consola como enviados. La contraseña de aplicación de Google requiere verificación en dos pasos y puede no estar disponible para algunas cuentas institucionales.

## Primera prueba real, separada de la cola

Tras configurar Gmail SMTP y con autorización para enviar **un solo** correo a una dirección bajo control del administrador, ejecutar desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend/manage.py enviar_correos_becas --prueba-a DIRECCION_CONTROLADA --confirmar-prueba
```

Esta prueba envía un mensaje sintético, sin datos de postulantes ni convocatorias, y no cambia la base. No ejecutar todavía el procesamiento de la cola. Para un envío operativo futuro se requiere habilitar expresamente el módulo, consentimiento de destinatarios y el comando `enviar_correos_becas --confirmar-envios --limite 10`; no hay tarea programada activada para correo.

Verificación aislada del 17/11/2026: ocho pruebas nuevas de correo y tres regresiones de notificaciones internas aprobaron en `test_becanexo_fusion_db`; las cinco pruebas focalizadas de la pantalla de notificaciones, Django check, lint, build y `git diff --check` aprobaron.

Verificación de fase 2: se respaldó `becanexo_db` con dump legible y 42 documentos comprobados por SHA-256; se aplicó únicamente `notificaciones.0002`. `migrate --check`, Django check y `git diff --check` aprobaron. Antes y después permanecieron 14 usuarios, 20 convocatorias y 47 notificaciones internas. Las tablas de preferencias y entregas quedaron vacías. No se enviaron correos reales.
