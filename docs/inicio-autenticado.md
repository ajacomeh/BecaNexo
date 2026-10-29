# Inicio autenticado

Actualizado el 28/10/2026. Ruta existente: `/inicio`, protegida por la sesión en App. Reutiliza ProfileLayout sin duplicar encabezado, menú, edición del nombre, cierre de sesión ni pie. Inicio queda activo mediante NavLink/aria-current. No cambia la bienvenida pública `/`, login ni retorno seguro.

El saludo usa el nombre actual del contexto de autenticación. Se eliminó la tarjeta redundante Tu cuenta y el texto Avance inicial; se mantiene la aclaración sobre postulación y verificación documental externa.

| Rol | Acceso | Ruta |
| --- | --- | --- |
| Postulante | Explorar becas | `/becas` |
| Postulante | Mi perfil | `/perfil` |
| Postulante | Idiomas y preferencias | `/preferencias` |
| Postulante | Mis favoritas | `/favoritos` |
| Administrador | Convocatorias | `/gestion/convocatorias` |
| Administrador | Entidades oferentes | `/gestion/instituciones` |
| Administrador | Rastreo | `/gestion/rastreo` |

Tarjetas semánticas con un enlace cada una, título como nombre accesible y descripción asociada. Reutilizan Icon/Lucide pendientes de la etapa anterior. Home.css limita todos sus selectores a home-dashboard: dos columnas en escritorio, una hasta 600 px, foco visible y texto adaptable. No añade estadísticas, indicadores ni operaciones. Los permisos del servidor y las rutas permanecen iguales.

## Verificación terminada

- Suite Vitest inicial: 107 casos, 105 aprobados y dos expectativas antiguas de texto fallidas. Se actualizaron exclusivamente esas expectativas a Convocatorias, dentro de Accesos de Inicio, conservando la comprobación de rol y añadiendo la ruta exacta.
- Repetición afectada: **30/30 aprobadas** en Home.test.jsx, Welcome.test.jsx y PublicAccess.test.jsx (3,89 s). Los otros **77 casos** aprobaron en la suite inicial, incluidos autenticación, edición del nombre, perfiles, favoritos, comparación y rastreo. Sin fallos pendientes. No se debilitaron las pruebas de retorno seguro.
- ESLint y build correctos. Pruebas nuevas de Inicio verifican tarjetas/rutas por rol, descripciones accesibles, ausencia de controles anidados, un único encabezado/pie/acciones de cuenta e Inicio activo.
- Edge, `playwright.home.config.js`: **6/6 aprobadas**, 20,3 s, secuenciales. Dos recorridos de Inicio con API simulada cubren ambos roles a 1440, 390 y 320 px: foco con Tab, cancelación sin petición, cambio del nombre en saludo/barra lateral, recarga y cierre de sesión. Las modificaciones están en memoria del mock, nunca en desarrollo. Las capturas revisadas no muestran desbordamientos ni superposiciones.
- El mismo recorrido incluye regresión de rastreo con API simulada, rechazo anónimo HTTP real de consulta/descarga y una prueba **sin interceptar la API** de visitante: `/inicio` dirige a `/login`; `/` sigue siendo público. No se comprobó una sesión personal real ni se modificaron cuentas.
- La prueba de navegación hacia Rastreo se acotó al menú principal: ahora también existe la tarjeta del mismo nombre, como exige el Inicio integrado.

Comandos desde frontend con Node 24 en PATH:

```powershell
npm.cmd test
npm.cmd test -- --run src/Home.test.jsx src/Welcome.test.jsx src/PublicAccess.test.jsx
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e -- --config playwright.home.config.js
```

Para revisión manual: abrir http://127.0.0.1:5173/inicio con cada rol, comprobar sus tarjetas y el menú activo, probar Editar nombre → Cancelar y recorrer enlaces con Tab. El cierre de sesión debe llevar al login. En ventana privada, `/` debe mostrar la bienvenida y `/inicio` exigir sesión. Pendiente únicamente la revisión visual del usuario con su sesión habitual.

Sin backend, dependencias nuevas, migraciones, datos, commits ni publicación. Se conservaron los cambios pendientes de iconografía.
