# Favoritos

App `favoritos`, tabla `REL_FAVORITO` según modelo v0.5: id, usuario_id, convocatoria_id y creado_en. Restricción PostgreSQL única usuario+convocatoria. Sin campos adicionales ni diferencias con el ER. Usuario se obtiene siempre de la sesión. No requiere perfil académico. No crea notificaciones ni recomendaciones.

| Endpoint | Método | Respuesta |
|---|---|---|
| `/api/favoritos/` | GET | 200, lista propia paginada `{count, page, page_size, results}` |
| `/api/favoritos/` | POST | Entrada exclusiva `{convocatoria: id}`; 201 al crear, 200 si ya estaba guardada, mismo ID y fecha |
| `/api/favoritos/<id_favorito>/` | DELETE | Sin campos; 204 al quitar un favorito propio, incluso si la oferta está oculta |

Solo postulantes autenticados. Administradores y anónimos reciben 403. Escrituras con sesión Django y CSRF real; campos de propietario, fecha o cualquier otro campo no permitido reciben 400. ID ajeno/inexistente al quitar: 404. Métodos no admitidos: 405 tras permisos/CSRF. Respuestas sin caché.

GET acepta solo page (desde 1) y page_size (12 por defecto, máximo 50); orden descendente por creado_en e id. Rechaza parámetros desconocidos, repetidos o inválidos. Página fuera de rango: lista vacía. No hay filtros de otros usuarios.

Agregar usa exactamente la visibilidad del catálogo (activa, revisión validada y oferente EC), con bloqueo de convocatoria, transacción y get_or_create respaldado por unicidad PostgreSQL. Borradores, pausadas y ofertas inexistentes reciben 404 incluso si ya estaban guardadas. Cerradas todavía públicas pueden guardarse y aparecen como cerradas.

Para una oferta disponible, cada resultado contiene id del favorito, creado_en, disponible=true y un resumen de convocatoria (id, título, institución, tipo, estado, cierre). Si deja de ser pública, se devuelve únicamente `{id, disponible: false, convocatoria: null, aviso: "Esta oportunidad ya no está disponible."}`. No se devuelve título, enlace, ID de convocatoria ni copia de datos antiguos. El favorito permanece hasta que su propietario lo quite; si vuelve a ser pública, vuelve a mostrarse su resumen.

Catálogo y detalle `/api/becas/` añaden `favorito_id` (ID propio o null) únicamente para postulantes autenticados. La consulta usa una subconsulta por propietario, no expone IDs de otros usuarios. El frontend obtiene siempre el estado desde PostgreSQL, sin guardarlo en localStorage. Los administradores no ven controles. Los visitantes ven un enlace «Guardar en favoritos» al login con retorno interno al detalle; no se guarda nada hasta que, autenticados, pulsen nuevamente. Validación del retorno en [consulta-publica.md](consulta-publica.md).

## Comprobación manual

Ingresar como postulante, abrir `/becas`, guardar una oferta y recargar. Debe aparecer «Quitar de favoritos» tanto en catálogo como en detalle. Abrir `/favoritos` desde «Mis favoritas», comprobar la oferta, cerrar e iniciar sesión y volver a comprobarla. Quitarla desde cualquiera de las pantallas y recargar: debe desaparecer del listado. Un fallo de API conserva el estado anterior y muestra el error, sin éxito anticipado.

Para comprobar ocultación, un administrador pausa una oferta guardada. Al recargar favoritos solo aparece el aviso, sin enlaces ni datos de esa oferta; el postulante puede quitarla. Reutilizar datos de demostración existentes para pruebas locales, sin atribuir ofertas ficticias a instituciones reales.

Las pruebas backend usan `manage.py test usuarios perfiles convocatorias favoritos --keepdb --verbosity 2` en test_becanexo_db, sin paralelismo. Estado de migración, resultados reales y pendientes en avance.md.

## Migración y recorrido automatizado

`backend/favoritos/migrations/0001_initial.py` crea únicamente REL_FAVORITO. Está aplicada en desarrollo tras aprobar pruebas. Para otra instalación, revisar primero `showmigrations favoritos` y `migrate favoritos --plan`; aplicar con `migrate favoritos --noinput` cuando corresponda. No requiere carga de catálogos ni datos de ejemplo nuevos.

Desde frontend/ con Node 24 portable en PATH, `npm.cmd run test:e2e -- e2e/favorites.spec.js` ejecuta el recorrido real sobre becanexo_db con Edge y los servidores locales. Requiere la convocatoria pública DEMOSTRACIÓN del módulo anterior; no la crea ni la modifica. Reutiliza las cuentas DEMO sin modificar sus campos y abre sesiones de fixture en memoria, sin contraseñas. Comprueba que no hubiera un favorito previo para esa cuenta/oferta antes de crear y quitar el suyo. Si ya existe, aborta para no borrar datos anteriores. La persistencia tras login real por correo y contraseña está cubierta por la prueba backend correspondiente.

Capturas y resultados en frontend/test-results, excluido de Git. Una pestaña abierta puede conservar su último estado hasta recargar: no se implementa actualización entre pestañas en tiempo real. El listado vuelve a consultar el estado de publicación al cargarse; nunca usa una copia persistida del título de una oferta oculta.
