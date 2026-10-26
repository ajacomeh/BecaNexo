# Bienvenida pública y rutas

La ruta `/` muestra la presentación propia de BecaNexo: encabezado, oportunidades de estudio, beneficios disponibles, cuatro pasos, invitación final y aclaración sobre postulación externa. Conserva Inter local y la paleta azul marino, azul y verde azulado de `diseno/BecaNexo_Interfaces_y_ER_v05.pdf` (presentación, página 2). La ilustración educativa es SVG decorativo local; no requiere descargas, paquetes ni servicios. No anuncia recomendaciones automáticas ni funciones futuras.

| Ruta | Acceso y comportamiento |
| --- | --- |
| `/` | Pública. Visitantes ven explorar, iniciar sesión y crear cuenta. Con sesión, los accesos de cuenta se sustituyen por Mi panel. |
| `/becas` | Catálogo público, filtros y paginación existentes. |
| `/becas/:id` | Detalle público solo de ofertas accesibles; postulación en la entidad oferente. |
| `/login` | Login existente. Logotipo enlaza a `/`. Retorno `next` validado al detalle, sin guardar favoritos automáticamente. |
| `/registro` | Registro existente. Logotipo enlaza a `/`. |
| `/inicio` | Panel protegido con navegación según rol. |
| `/perfil`, `/preferencias`, `/favoritos` | Protegidas y exclusivas del postulante. |
| `/gestion/*` | Administración protegida según permisos existentes. |

No se cambian permisos, sesiones, protección CSRF ni la validación de retornos. La restauración de sesión existente sigue mostrando carga y opción de reintento ante errores de conexión.

## Verificación reproducible

Con Node 24 en PATH, desde `frontend/`: `npm.cmd test`, `npm.cmd run lint`, `npm.cmd run build` y `npm.cmd run test:e2e -- --config playwright.public.config.js`.

La configuración pública ejecuta únicamente `e2e/public.spec.js`, con un trabajador. Reutiliza servidores disponibles o inicia los configurados. Necesita una convocatoria pública existente; no crea datos para satisfacer esa condición.

- Navegación anónima real por bienvenida, login, registro, catálogo y detalle, con cero escrituras a la API.
- Panel y retorno tras login en navegador mediante respuestas de autenticación interceptadas. Las escrituras adicionales se abortan y hacen fallar la prueba. Esto verifica la navegación del cliente sin crear sesiones de Django ni modificar `last_login`; no constituye una nueva prueba de autenticación real de extremo a extremo.
- Capturas a 1440, 390 y 320 píxeles y comprobación de ausencia de desbordamiento horizontal. Se comprueba navegación inicial con Tab; los enlaces usan el foco visible existente. Las capturas quedan en `frontend/test-results/`, excluido de Git.
- La suite frontend incluye retorno seguro, separación por rol y protección de rutas, además de seis casos de bienvenida.

Revisión visual realizada en Edge; no equivale a una auditoría completa de accesibilidad, dispositivos físicos o todos los navegadores. No se modifica la base de datos ni se aplican migraciones.
