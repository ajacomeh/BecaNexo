# Consulta pública de becas

La ruta `/` presenta la bienvenida pública. Sus accesos, diseño y rutas se documentan en [bienvenida.md](bienvenida.md).

El catálogo `/becas` y detalle `/becas/:id` ya permitían visitantes, al igual que sus endpoints GET `/api/becas/`, `/api/becas/:id/` y `/api/becas/catalogos/`. Se conservan filtros, paginación y reglas existentes: activa, revisión validada y oferente ecuatoriano. Borradores y pausadas nunca aparecen y devuelven 404 por ID. Las cerradas publicadas conservan su estado de cierre.

Se mantienen los enlaces públicos de iniciar sesión y crear cuenta y la navegación por rol. Perfil, preferencias, favoritos y administración siguen protegidos en frontend y backend; no se cambia CSRF ni los permisos de escritura.

## Enlace oficial

El detalle ofrece «Ir al sitio oficial», accesible sin cuenta, junto a «La postulación se realiza en la plataforma de la entidad oferente.». Abre la URL HTTP/HTTPS registrada en otra pestaña con noopener/noreferrer. El backend no descarga esa URL. BecaNexo no tramita la postulación.

## Favoritos y regreso del login

Un visitante ve «Guardar en favoritos» como enlace a `/login?next=%2Fbecas%2F<id>`, tanto en catálogo como en detalle. El parámetro sobrevive a una recarga del login. No se envía una petición de guardado ni se almacena una acción pendiente. Después del login se vuelve al detalle; guardar requiere pulsar otra vez el botón como postulante. Los administradores siguen sin controles de favoritos.

`auth/returnPath.js` valida next en un único lugar, tanto al completar login como al entrar al login con una sesión ya existente. Solo acepta exactamente `/becas` o `/becas/` seguido de un entero positivo, hasta 100 caracteres. No acepta dominios, doble barra inicial, contrabarras, rutas administrativas, query, fragmentos, caracteres de control, rutas relativas ni next repetidos. No hay una segunda decodificación. Un retorno ausente o rechazado usa `/inicio`. No se agrega soporte de retorno a registro en este ajuste.

Las respuestas públicas ya omitían revision, activa, version y clave de deduplicación de la convocatoria; ahora también omiten activa de las opciones y activo/validado de los requisitos. Se conservan sus condiciones públicas, ámbito, forma de comprobación y fecha de actualización. La consulta administrativa permanece intacta.

## Verificación

Las pruebas de integración del frontend simulan exclusivamente la API para verificar login, retorno, sesión existente, roles, rutas protegidas y ausencia de guardado automático. Las pruebas backend usan test_becanexo_db con --keepdb y comprueban publicación, filtros/paginación, no exposición por ID y permisos.

El recorrido `npm.cmd run test:e2e -- --config playwright.public.config.js` abre Edge sin sesión y consulta una oferta pública existente, aplica búsqueda, abre su detalle, comprueba el enlace oficial, entra al login desde favoritos y conserva next al recargar. Esta configuración solo selecciona public.spec.js y permite reutilizar los servidores locales activos; los otros recorridos mantienen su configuración independiente. Solo hace GET a las APIs: no inicia sesión real, crea cuentas, guarda favoritos, modifica ofertas ni visita el sitio externo. El login y retorno completos se prueban en integración frontend; la autenticación real se mantiene cubierta en backend. Se ejecuta este recorrido específico para respetar la prohibición de modificar datos existentes, sin ejecutar los otros recorridos que crean demostraciones.

El archivo de recorridos públicos también incluye bienvenida adaptable y navegación al panel/retorno con autenticación interceptada en el navegador. Estas respuestas simuladas impiden escrituras de sesiones o usuarios en desarrollo; el resto de consultas públicas usa la API real. Véase bienvenida.md.

No hay migraciones ni modificaciones del respaldo. Resultados reales en avance.md.
