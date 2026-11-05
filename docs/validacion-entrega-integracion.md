# Validación de entrega: integración y pruebas preliminares

## Base, alcance y conclusión

Commit base: `9145be7305f7463b742339cc4685a844cb6d16a0` (`9145be7`). Este informe consolida la ejecución iniciada el 04/11/2026 y su continuación; no suma resultados de etapas anteriores. Se revisaron AGENTS, configuración, rutas, código relacionado, documentación y Git. La guía `GUIA_ARQUITECTURA_BECANEXO.md` se conserva sin seguimiento y fuera de los cambios de este cierre.

**La versión puede presentarse como integración de las funciones existentes, con límites explícitos.** No se detectó un fallo de aplicación bloqueante en los flujos verificados. Existe una limitación de datos de demostración: la convocatoria A (ID 4) está en borrador y no debe presentarse como pública ni como el escenario original intacto. El recorrido propuesto evita esa dependencia. No se certifica un porcentaje de desarrollo, seguridad de producción ni cobertura total.

Cambios posteriores al commit base realizados para este cierre:

- `frontend/src/EditName.test.jsx`: desmontar los componentes antes de retirar los métodos de diálogo simulados; no cambia la aplicación.
- `frontend/e2e/reviews.spec.js`: pruebas controladas de carga, conflicto 409, fallo 500 al consultar, conservación del texto y recuperación por teclado.
- `frontend/e2e/integration_server.py` y `integration-real.mjs`: versión reproducible y protegida del recorrido con Django real, antes ubicada en una carpeta de resultados ignorada.
- `frontend/e2e/run-reviews.mjs`: ejecutor que administra su propio Vite en el mismo proceso y reutiliza una instancia existente del proyecto sin cerrarla.
- Este informe y una nota en `avance.md`. Sin cambios de modelos, reglas de negocio o código de aplicación; sin commits, despliegue ni escrituras en desarrollo.

## Funcionalidades y estado real

| Área | Implementado y verificado | Límite o pendiente |
| --- | --- | --- |
| Cuenta y seguridad | Registro/login por correo, sesiones Django, CSRF, cierre, nombre visible, permisos por rol, rechazo anónimo/inactivo y entradas no permitidas mediante regresión | La limitación de intentos usa caché local por proceso. HTTPS y operación distribuida no se certifican en esta entrega local |
| Perfil | Nacionalidad explícita EC, nombre en Usuario, descripción opcional hasta 1500 caracteres, formaciones, experiencia actual con fin nulo, idiomas y preferencias; conservación y validaciones | Datos declarados; no acredita títulos, documentos ni idiomas. No recibe archivos de postulantes |
| Catálogo | Consulta pública, filtros combinados por opción, paginación, detalle, enlaces oficiales, documentación común/por opción y favoritos propios | No realiza postulaciones ni adjudicación; la entidad oferente recibe/verifica documentos |
| Comparación | Reglas explícitas, desconocidos separados de incumplimientos, misma formación, destinos, explicación y verificación documental externa pendiente | Sin recomendación semántica, afinidad o porcentaje de adjudicación. Conversiones de promedio y cómputo de meses requieren reglas aprobadas |
| Administración | Oferentes, convocatorias, opciones/destinos, beneficios, requisitos documentales, revisión/publicación manual y auditoría | El editor no debe usarse para ensayar escrituras en datos reales durante la presentación |
| Rastreo | Captura técnica SIAU, acceso controlado, archivo privado, identidad/URL, versiones y observaciones; consulta administrativa y revisiones independientes, rectificación/concurrencia | No integra publicaciones al catálogo, no programa capturas diarias ni publica automáticamente. Aprobar convenios continúa bloqueado |
| Revisión sustantiva de las fuentes | La interfaz y el backend permiten registrar decisiones sobre evidencia exacta | En la lectura real de desarrollo se encontraron **cero revisiones editoriales**. Tener el mecanismo implementado no significa haber aprobado SIAU |
| Funciones posteriores | — | IA/afinidad, integración rastreo-catálogo y notificaciones no implementadas en esta tarea |

Referencias: `usuarios/api.py`, `perfiles/api.py` y serializers, `convocatorias/services.py`, `reglas.py`, `comparacion.py`, `favoritos/api.py`, `rastreo/revisiones.py`, rutas de cada app y `frontend/src/App.jsx`.

## Resultados actuales y comandos

Ejecutados secuencialmente. Las pruebas con escrituras usaron exclusivamente `test_becanexo_db`; la suite no se ejecutó en paralelo. Algunos casos de concurrencia abren conexiones/hilos como parte de su propio escenario.

| Comprobación | Resultado final de esta ejecución |
| --- | --- |
| Django check | Sin incidencias |
| `makemigrations --check --dry-run` | Sin cambios de modelo |
| `showmigrations` y `migrate --plan` (lectura en desarrollo) | Todas aplicadas; ninguna operación pendiente. Confirmada `perfiles.0002_perfil_descripcion`, además de rastreo 0006/0007 |
| Backend completo: usuarios, perfiles, convocatorias, favoritos y rastreo | **210 pruebas aprobadas**, 180,841 s; 0 fallidas/omitidas |
| Frontend completo, 14 archivos | **125 pruebas aprobadas**, 59,66 s en la ejecución final; 0 fallidas/omitidas |
| Playwright: revisión administrativa simulada | **3 escenarios aprobados**, 1440/390/320 px, 9,1 s tras ampliar las comprobaciones; código 0 |
| Recorrido aislado con Django real | Completado; ejecutor reutilizable código 0. No se suma como un número inventado de casos unitarios |
| ESLint | Correcto, repetido tras incorporar los ejecutores reutilizables |
| Build Vite | Correcto. No repetido al continuar porque después solo cambiaron pruebas y documentación, no el bundle de aplicación |

La primera suite frontend dio 124 aprobadas y un fallo de limpieza del diálogo. Tras corregirlo, se repitió completa: el total final es **125**, no 249. Los intentos fallidos de preparación o de simulación tampoco cuentan como casos adicionales aprobados.

Desde la raíz, con el entorno ya preparado y sin imprimir `.env`:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py showmigrations
.\.venv\Scripts\python.exe backend\manage.py migrate --plan
.\.venv\Scripts\python.exe backend\manage.py test usuarios perfiles convocatorias favoritos rastreo --keepdb --verbosity 1

$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
Push-Location frontend
npm.cmd test -- --no-file-parallelism
npm.cmd run lint
npm.cmd run build
Pop-Location
```

Antes de la suite se comprobó que TEST.NAME es `test_becanexo_db`, distinto de NAME, y que no hay TEST.MIRROR. **`migrate --plan` no aplicó migraciones.** No ejecutar un `migrate` sobre desarrollo como parte de este informe.

## Integración real, simulación y revisión humana

### Django/PostgreSQL reales, aislados

El navegador usa React real y redirige únicamente el transporte `/api/` a Django en `127.0.0.1:8765`; `route.fetch` obtiene respuestas reales y las entrega al navegador. No inventa respuestas de negocio. Hay sesiones/cookies y CSRF reales; no se inyectó un usuario autenticado en memoria para este recorrido.

Se comprobaron:

- Login de postulante y administrador sintéticos, logout e invalidación de sesión; denegaciones anónimas, por rol y escritura sin CSRF.
- Guardado de nombre y descripción desde el perfil, actualización y recarga; rechazo servidor de nacionalidad no EC y descripción excesiva.
- Experiencia actual con fecha final nula, rechazo de PATCH incoherente, consulta y campo deshabilitado al editar.
- Consulta de formaciones, idiomas y preferencias; comparación real de requisitos.
- Catálogo, guardar favorito, recargar y quitarlo desde favoritos.
- Alta documental sintética por API administrativa, rechazo de URL insegura y edición visual del registro correcto. Perfil y editor revisados a 1280/390/320 px con teclado y textos extensos.
- Consulta y registro de revisión de extracción pendiente, y visualización de su historial en el navegador, exclusivamente sobre evidencia sintética en pruebas.

La creación general de oferentes/opciones/beneficios, publicación y conflictos concurrentes también se cubrieron con la suite backend contra PostgreSQL; no se afirma haber repetido toda esa administración manualmente en el navegador. Las peticiones específicas de validación se emitieron desde el navegador; no todas se introdujeron mediante el formulario.

La fuente de pruebas se prepara mediante el servicio real con `Downloader.once` sustituido por bytes de fixtures. **No hubo consultas a SIAU ni descargas externas.** Los documentos se guardaron en un directorio temporal independiente del archivo documental real. El uso de ese fixture no constituye revisión sustantiva de SIAU.

El proxy habitual Vite→Django:8000 no se certifica mediante este desvío de transporte; antes de la reunión debe comprobarse su disponibilidad local con la sesión del usuario. Tampoco se simularon fallos reales de red contra desarrollo.

### API simulada y pruebas de componentes

Las 125 pruebas de React usan dobles de API según cada caso: verifican estados, errores, guardados parciales de perfil/nombre, conservación de campos, datos antiguos, navegación, permisos representados en interfaz, favoritos, comparación y revisión. No sustituyen las pruebas de permisos del servidor.

Los tres recorridos de bandeja usan API simulada: carga retenida, justificación obligatoria, bloqueo durante POST, conflicto 409, texto conservado, fallo 500 al refrescar, guardado deshabilitado hasta recuperar datos, reintento por Enter, éxito e historial. Capturas revisadas en escritorio y móvil; sin desbordamiento observado y con foco visible. La UI no muestra aprobación sin una decisión registrada. No se guardó una revisión real de desarrollo para demostrarlo.

### Confirmación manual del usuario

El usuario confirmó previamente que los requisitos se guardan, consultan y editan correctamente y revisó las correcciones del editor. También consta su revisión anterior de acceso a la bandeja y apertura/cancelación de revisión sin guardar decisiones. Son **confirmaciones del usuario**, no comprobaciones nuevas ejecutadas por el agente ni casos añadidos a los totales.

## Ejecutores reproducibles y aislamiento

`frontend/test-results/` está ignorado por Git y es una salida que Playwright puede limpiar. Los scripts originales allí no son la fuente mantenida. Se conservan versiones sin credenciales en:

- `frontend/e2e/integration-real.mjs`: orquesta Edge, servidor aislado y Vite.
- `frontend/e2e/integration_server.py`: preparación y servidor contra la base de pruebas.
- `frontend/e2e/run-reviews.mjs`: bandeja con API simulada; no inicia Django.

```powershell
# Recorrido real: reinicia SOLO los datos de test_becanexo_db.
# No ejecutar mientras otra suite o persona esté usando esa base de pruebas.
& 'D:\Herramientas\node-v24.22.1-win-x64\node.exe' frontend/e2e/integration-real.mjs --reset-test-db

# Bandeja con API simulada, sin escrituras de base de datos:
& 'D:\Herramientas\node-v24.22.1-win-x64\node.exe' frontend/e2e/run-reviews.mjs
```

Requieren dependencias ya instaladas, Edge y la base de pruebas previamente preparada por el runner Django. No instalan paquetes ni aplican migraciones. El primer comando exige la bandera de reinicio, fija NAME antes de inicializar Django, comprueba `SELECT current_database()` y **solo entonces** ejecuta `flush` en pruebas y crea fixtures. Reinicia datos de pruebas, no elimina/reconstruye la base ni altera credenciales de PostgreSQL. No es un comando de demostración para desarrollo.

El backend aislado rechaza una carpeta que no sea temporal propia; el archivo real `D:\Datos_BecaNexo\rastreo` no se utiliza. Contraseñas aleatorias solo en memoria/entrada del proceso; sesiones del navegador no se exportan. Al finalizar, se cierran el navegador y el backend propios, se cierra Vite solo si lo inició el ejecutor y se elimina únicamente su directorio temporal validado. Los registros sintéticos quedan en la base de pruebas hasta su próximo reinicio; sus documentos temporales no son un archivo histórico persistente.

Antes de iniciar se exige libre el puerto 8765 y se verifica que una instancia existente en 5173 sirva BecaNexo; no se detiene una instancia ajena. Capturas y resultados permanecen ignorados en `frontend/test-results/`; no incorporar cookies, documentos de prueba ni salidas generadas al repositorio.

## Incidencias y soluciones

1. **Limpieza del diálogo en Vitest:** `element.close is not a function` al retirar el mock antes del desmontaje. Se ordenó `cleanup()` antes de restaurar/eliminar los métodos; suite final completa aprobada. No se debilitó la validación de doble envío.
2. **Preparación del recorrido real:** el primer password sintético incumplía similitud y la fuente se intentaba activar antes de registrar. Se corrigió el fixture para respetar las validaciones, sin cambios de negocio. Un selector de prueba demasiado exacto no encontraba Nacionalidad con su indicador obligatorio; se corrigió al control por nombre. El recorrido original se completó por bloques y la versión reutilizable se ejecutó después completa con código 0.
3. **Simulador ampliado de revisiones:** contar GET causaba un 500 durante el montaje duplicado de StrictMode. Se modelaron fases vinculadas a las acciones del usuario; carga se comprueba mediante `aria-busy`, no suponiendo un cambio de texto del botón. Los tres casos finales aprobaron.
4. **Cierre de auxiliar Windows:** un intento fallido dejó Playwright esperando al Vite lanzado a través de shells npm. Se comprobó la cadena de PID y se cerró únicamente ese Vite; el ejecutor fallido terminó con código 1. El nuevo wrapper mantiene Vite en su proceso y el recorrido final terminó con código 0. No se detuvo un servidor personal.
5. **Lint de los nuevos `.mjs`:** se declararon los globales utilizados en el contexto del navegador. Lint final aprobado; no cambia el comportamiento de la aplicación.

## DEMOSTRACIÓN A: lectura real, sin restauración

Consultada en transacción PostgreSQL `READ ONLY`: ID **4**, título **DEMOSTRACIÓN A · Coincidencias**, `activa=true`, `revision=pendiente`, estado calculado **borrador**, excluida de la consulta pública. Tiene **8 requisitos frente a 7 originales**: se agregó el requisito común **57**, tipo **12**, sin revisar. Los siete requisitos previos, las opciones y los beneficios coinciden con la instantánea de creación; también difieren título, versión, representación de institución y fecha de actualización. El título original era «DEMOSTRACIÓN · REVISIÓN DE AVANCES · A · Coincidencia declarada».

No se editó, restauró ni publicó. Para mostrar otra vez el escenario A original hace falta una decisión y una tarea expresamente autorizada; este cierre no las supone. En la misma lectura estaban abiertas las ofertas **1, 2, 5, 6, 7 y 8**; la 3 estaba pausada. Son hechos observados, no promesa de estado futuro.

## Recorrido propuesto de presentación: 9 minutos

Preparar antes dos sesiones/ventanas con roles autorizados, sin compartir contraseñas. Usar la cuenta sintética de reunión ya existente, no modificarla para automatizar. La variante de desarrollo siguiente es de **consulta**: las escrituras de ejemplo se demuestran con las pruebas aisladas y su evidencia, no con aprobaciones o publicaciones reales.

| Tiempo | Acción | Resultado esperado |
| --- | --- | --- |
| 0:00–1:00 | Abrir `/` y `/becas` sin sesión; aplicar un filtro conocido | Bienvenida y catálogo públicos; no hay controles administrativos |
| 1:00–2:00 | Abrir `/becas/1` o `/becas/2` | Información, opciones, beneficios y documentación registrada; enlace oficial y aviso de postulación externa |
| 2:00–3:00 | Con sesión postulante, abrir `/inicio` y `/perfil` | Nombre real de la cuenta, nacionalidad, descripción y datos declarados; explicar edición sin pulsar Guardar |
| 3:00–4:00 | Consultar formaciones/experiencia y `/preferencias` | Experiencia actual sin fecha final, idiomas declarados y preferencias; no certificados recibidos |
| 4:00–5:30 | Consultar `/becas/7` y su comparación con la cuenta sintética de reunión | Resultados por opción, coincidencias/incumplimientos/pendientes y explicación. Si los datos del perfil cambiaron, mostrar el resultado actual sin forzarlo |
| 5:30–6:00 | Abrir `/favoritos` y mostrar evidencia del recorrido guardar→recargar→quitar en pruebas | Lista propia o estado vacío; no inventar favoritos ni crearlos en desarrollo para la demostración |
| 6:00–7:00 | Cambiar a sesión administradora: `/gestion/convocatorias` y `/gestion/convocatorias/4` | A se muestra explícitamente como borrador. Consultar requisitos y abrir/cancelar edición; explicar ámbito común y revisión de transcripción, sin guardar/publicar |
| 7:00–8:30 | `/gestion/rastreo`, publicaciones 1/2 y ejecuciones | Procedencia, versión y documentos exactos. Abrir/cancelar Registrar revisión. Pendiente no equivale a aprobada; la ejecución 1 no requiere publicaciones retrospectivas |
| 8:30–9:00 | Mostrar este informe y la separación entre comparación y funciones futuras | Resumen de pruebas actuales y límites: sin IA, sin integración al catálogo ni publicación automática |

Si una oferta prevista ya no está pública, volver al catálogo y elegir una visible; nunca publicarla de improviso. No usar `/becas/4` como paso exitoso.

## Bloqueos, pendientes y siguiente etapa

- **Presentación:** no hay bloqueo técnico conocido para mostrar el alcance probado. Sí está bloqueada la demostración pública de A en su estado actual. Usar el recorrido anterior.
- **Antes de la reunión:** comprobar disponibilidad de Django:8000 y Vite:5173, las sesiones propias y las rutas elegidas. Este cierre no conserva cuentas de acceso del runner ni servidores de pruebas activos. Una validación con sesión personal la realiza el usuario, no la automatización.
- **Límites de verificación:** Edge local; no se certifican otros navegadores, auditoría completa con lector de pantalla, carga, HTTPS productivo, seguridad distribuida ni restauración de respaldos. No se restauraron respaldos. Los fallos visibles de la bandeja fueron simulados; las reglas y permisos se probaron también en PostgreSQL real.
- **Rastreo → catálogo:** falta el flujo de propuesta y vinculación/creación de convocatoria canónica con evidencia exacta revisada, mapeos explícitos de oferente/opciones/requisitos/beneficios y control de obsolescencia frente a correcciones manuales. Hay que acordar la representación de precisión de fechas sin inventar horas y topes/moneda, y la evidencia de convenios antes de admitirlos. La aplicación debe conservar la versión pública mientras se revisan cambios, aplicar solo diferencias aprobadas y auditar la integración. Publicación, vigencia y revisión documental siguen siendo decisiones distintas.
- El primer paso siguiente es concretar y aprobar ese contrato de integración y sus pruebas de concurrencia/idempotencia, **no activar automáticamente publicaciones ni implementar IA**. La propuesta de persistencia contiene diseño futuro; sus tablas propuestas no deben presentarse como existentes.
