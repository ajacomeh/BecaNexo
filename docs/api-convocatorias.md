# Convocatorias y catálogo

## Decisiones del modelo

Se implementan las nueve entidades solicitadas y AUD_EVENTO. Se reutilizan CAT_PAIS, CAT_AREA y CAT_IDIOMA y los dominios de nivel/modalidad de perfiles. No se crean ejecuciones de rastreo para entradas manuales.

`revision` admite `pendiente` y `validada`, términos de las pantallas 17–18. Es revisión administrativa, no vigencia temporal. Una convocatoria se consulta públicamente solo con revisión validada, activa=True y oferente EC. Crear y editar (también detalles u oferente) deja revisión pendiente; publicar valida y marca validada/activa; pausar pone activa=False sin borrar. Volver a publicar realiza todas las validaciones. No se introduce un estado de archivo ajeno al diseño: la pausa conserva datos e historial.

El estado calculado distingue borrador, pausada, próxima, abierta, cerrada y sin_fecha. Al alcanzar exactamente el instante de cierre se considera cerrada. Se usa America/Guayaquil y datetimes con zona; cierre NULL no afirma que esté abierta. Las cerradas publicadas permanecen consultables, claramente identificadas.

AUD_EVENTO mantiene actor obligatorio, acción, cambios y fecha. Adaptación explícita del ER: se implementa la referencia opcional a convocatoria, se añade institución opcional y una restricción XOR exige exactamente una de las dos. Fuente y configuración de motor se posponen junto a sus módulos (no se crean columnas sin FK ni registros ficticios). Cuando se incorporen, será necesaria una migración que amplíe el XOR. La institución adicional permite auditar su creación antes de existir una convocatoria. Se registran instantáneas antes/después, origen manual, identificador del actor y momento; no credenciales ni datos del perfil. El enlace oficial y las referencias de las bases conservan procedencia manual; TRA_PUBLICACION_FUENTE requiere ejecución real y se reserva al rastreo.

En borrador descripción y URL oficial admiten cadena vacía (no NULL); al publicar son obligatorias. Se mantienen obligatorios título e institución incluso en borrador. Los char(64)/char(3) del ER se implementan mediante varchar de longitud limitada, como en perfiles. Los catálogos y reglas son datos declarados: no se verifica documentación de postulantes.

La publicación exige oferente ecuatoriano, título, descripción, URL HTTP/HTTPS, al menos una opción activa y todos los requisitos activos revisados. No exige inventar tipos, fechas, destinos, beneficios ni requisitos ausentes. Las reglas duplicadas escalares aplicables a una misma opción se deben unificar; idiomas y experiencias se distinguen por idioma/área. Beneficios con igual concepto en ámbitos superpuestos se resuelven registrando el resultado por opción antes de publicar, sin sumar porcentajes comunes y específicos.

Las clasificaciones iniciales Mérito académico e Investigación proceden del prototipo y no son una taxonomía exhaustiva. Los 13 contratos se derivan de Reglas_y_requisitos.md; los nombres concretos de claves de acreditación/documentos/residencia y operadores se fijan en `reglas.py` versión 1. No se interpreta código ni JSON arbitrario.

## API y seguridad

Prefijo `/api/`, barra final y JSON. Las escrituras requieren sesión activa, rol de negocio `administrador` y CSRF. `is_staff` no autoriza estas rutas. Consulta pública GET disponible también sin sesión. Respuestas sin caché; las URLs aceptan solo HTTP/HTTPS sin credenciales y no se consultan desde el backend. React presenta texto sin interpretar HTML.

| Ruta relativa | Métodos | Respuesta |
|---|---|---|
| `becas/catalogos/` | GET | 200: países, idiomas, áreas, dominios, tipos de beca y contratos de requisitos |
| `becas/` | GET | 200: convocatorias públicas paginadas |
| `becas/<id>/` | GET | 200: detalle público; 404 si no existe, es borrador o está pausada |
| `gestion/instituciones/` | GET, POST | Lista paginada / creación 201 |
| `gestion/instituciones/<id>/` | GET, PATCH | Lectura / actualización 200 |
| `gestion/convocatorias/` | GET, POST | Lista administrativa paginada / borrador 201 |
| `gestion/convocatorias/<id>/` | GET, PATCH | Detalle / edición 200, vuelve a pendiente |
| `gestion/convocatorias/<id>/opciones/` | GET, POST | Lista paginada / creación 201 |
| `gestion/convocatorias/<id>/beneficios/` | GET, POST | Lista paginada / creación 201 |
| `gestion/convocatorias/<id>/requisitos/` | GET, POST | Lista paginada / creación 201 |
| Cada colección hija + `<id>/` | GET, PATCH | Lectura / edición 200 |
| `gestion/convocatorias/<id>/beneficios/<id>/` | DELETE | 204; conserva la instantánea en auditoría |
| `gestion/convocatorias/<id>/publicar/` | POST sin campos | 200 tras validar todos los mínimos |
| `gestion/convocatorias/<id>/pausar/` | POST sin campos | 200; conserva revisión e historial |
| `gestion/convocatorias/<id>/auditoria/` | GET | Historial paginado, solo administrador |

No se permite borrar convocatorias ni instituciones. Para opciones se edita `activa`, para requisitos `activo`; DELETE sobre ellos devuelve 400 indicando desactivar. Un método fuera de las operaciones admitidas produce 405 después de comprobar permisos/CSRF. 400 para campos desconocidos, errores, duplicados y filtros inválidos; 403 para rol/sesión/CSRF; 404 para objetos inexistentes o hijos de otra convocatoria. OPTIONS está disponible. JSON inválido/tipo de contenido: 400/415 de DRF.

Institución: nombre, sector (`publico`/`privado`), pais (ID de Ecuador) y url_oficial opcional. Convocatoria acepta los campos de negocio del modelo, con `institucion` y `tipo_beca` como IDs y `areas` como lista sin duplicados de IDs de CAT_AREA. Rechaza revision, activa, version, actualizado_en, clave_deduplicacion, id y campos de auditoría en escrituras. Los cambios de estado usan las acciones dedicadas.

Opción acepta nivel, modalidad, activa, programa, institucion_destino, inicio_estudios, duracion_meses, cupos y paises (IDs sin duplicados). Su identidad es convocatoria+nivel+modalidad, también restringida en PostgreSQL. Cupos y duración son positivos si se informan. País oferente y países destino son conceptos distintos.

Beneficio acepta opcion_estudio opcional (NULL=común), concepto, porcentaje 0–100, monto no negativo, moneda requerida si hay monto, periodicidad (`unico`, `mensual`, `anual`, `otra`) y detalle. La moneda es un código de tres letras mayúsculas: no se convierte moneda ni se mantiene un catálogo monetario en esta etapa. No se asigna cobertura total a partir de un porcentaje por concepto.

Requisito acepta los atributos del modelo salvo propietario/id. El administrador selecciona el tipo y completa controles específicos; el cliente construye valor_estructurado y el servidor valida todas sus claves y tipos contra el contrato versionado. Operador se deriva del tipo si se omite; un operador incompatible se rechaza. Fecha de referencia obligatoria para edad; escalas y rangos coherentes; título requiere estudios concluidos. ACREDITACION, DOCUMENTO y OTRO usan exclusivamente entidad_oferente; los demás tipos usan dato_declarado. Los certificados constituyen condiciones externas separadas de idioma/nivel. NULL conserva ausencia de información, nunca se transforma en cero o False.

Se bloquea la convocatoria durante escrituras de detalles y se incrementa su versión junto con la auditoría dentro de la transacción. Las escrituras de oferente invalidan la revisión de sus convocatorias y registran eventos. La API no recibe el propietario de un hijo; verifica que la opción pertenezca a su convocatoria. La clave de deduplicación es SHA-256 de institución, título normalizado y URL oficial; no intenta fusionar ofertas parecidas. Un conflicto concurrente de unicidad devuelve 400 con rollback. Estas garantías corresponden a estas rutas: futuros procesos de importación deberán utilizar servicios equivalentes, no escribir directamente saltándose validaciones/auditoría.

## Filtros y paginación

Listas: `{count, page, page_size, results}`. Página desde 1; 12 elementos por defecto, máximo 50. Consultar páginas fuera del total devuelve lista vacía. Instituciones acepta q por nombre. Convocatorias acepta q (título, institución o área; máximo 200 caracteres), nivel, modalidad, destino (código ISO), tipo_beca (ID), estado y orden (`recientes`, `titulo`, `cierre`). Las fechas de cierre NULL se ordenan al final. El listado administrativo además acepta revision. Parámetros desconocidos o repetidos se rechazan.

Filtros nivel+modalidad+destino se aplican en una única subconsulta a opciones activas: nunca se combina nivel de una opción con destino de otra. Consulta pública no admite filtros de borrador/pausada; no devuelve opciones ni requisitos inactivos. Los catálogos de referencia completos son acotados y no se paginan; los detalles muestran todas las condiciones de una convocatoria para no ocultar requisitos relevantes.

## Carga y ejecución

Desde la raíz, PostgreSQL configurado en backend/.env sin imprimir sus valores:

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py showmigrations convocatorias
.\.venv\Scripts\python.exe backend\manage.py migrate --plan
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe backend\manage.py test usuarios perfiles convocatorias --keepdb --verbosity 2
# Tras validar el plan aditivo en el entorno correspondiente:
.\.venv\Scripts\python.exe backend\manage.py migrate convocatorias --noinput
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos_convocatorias
```

La carga actualiza contratos por código y crea clasificaciones por nombre si faltan; preserva IDs y no elimina filas. No duplica países, idiomas ni áreas. No crea ofertas ni cuentas. Las pruebas backend usan únicamente test_becanexo_db y no se ejecutan con --parallel. Para frontend se usa Node 24 portable con los comandos de `ejecucion-local.md`: lint, test y build.

## Flujo manual reproducible

1. Arrancar Django y Vite siguiendo `ejecucion-local.md`; mantener el origen CSRF local configurado. Ingresar con una cuenta administradora existente.
2. Inicio → Gestionar convocatorias → Gestionar oferentes. Registrar nombre, sector, Ecuador y enlace institucional. No usar una entidad real para representar una demostración ficticia.
3. Crear convocatoria: título, oferente, descripción y enlace oficial. Guardar borrador. Completar opcionalmente tipo, fechas en America/Guayaquil, bases, cobertura, gastos, obligaciones y áreas.
4. Añadir opciones de estudio con nivel/modalidad, países y datos conocidos. Añadir beneficios por concepto y ámbito. Añadir requisitos por tipo, sus condiciones y texto original; marcar revisión solo después de cotejar las bases. Documentos y certificados se verifican externamente.
5. Validar y publicar. Un error conserva los datos y no muestra éxito. Un requisito sin revisar o beneficio superpuesto bloquea la publicación. Usar «Ver en el catálogo» al aprobar.
6. En otra sesión, ingresar como postulante → Explorar becas, aplicar filtros y consultar detalle. No se muestran puntuaciones, favoritos ni recomendaciones.
7. Como administrador editar y guardar una sección: la oferta vuelve a pendiente y devuelve 404 en consulta. Publicar de nuevo; recargar como postulante y comprobar el cambio. Pausar debe retirarla sin eliminarla. Una cerrada publicada se conserva con aviso de cierre, nunca como abierta.

## Demostración automatizada local

`npm.cmd run test:e2e` utiliza Edge, servidores locales y becanexo_db. `offers.spec.js` conserva una única convocatoria titulada «DEMOSTRACIÓN · BecaNexo catálogo local» y una entidad «DEMOSTRACIÓN · Entidad ecuatoriana ficticia», con enlaces example.org. Busca ambas antes de crearlas y reutiliza la demostración existente. La oferta y sus detalles quedan disponibles para inspección; la creación de ejemplos no forma parte del comando de catálogos.

El helper exclusivo de pruebas `e2e/bootstrap_ofertas.py` crea solo si faltan dos cuentas claramente identificadas (administrador/postulante), sin contraseña utilizable, is_staff=False e is_superuser=False. Si una cuenta existente no coincide con la fixture, aborta sin modificarla. Prepara sesiones de prueba en memoria mediante Django y el recorrido las cierra al terminar; no imprime ni guarda cookies. No altera el superusuario ni cuentas anteriores. Este recorrido prueba los permisos de sesión; el inicio de sesión real por contraseña está cubierto por el recorrido de autenticación independiente.

El recorrido administra opciones/destinos, beneficio del 80 % de matrícula y condición documental externa, publica, consulta como postulante, edita y republica. Capturas en frontend/test-results (ignorado); sin trazas ni vídeos. Los otros recorridos de autenticación/perfil conservan sus cuentas desechables descritas en la guía local.

Resultados ejecutados y migraciones aplicadas se registran en `avance.md`; no se considera una prueba aprobada por estar solamente escrita. Pendientes de producción: auditoría completa de accesibilidad, otros navegadores, pruebas de carga, HTTPS/cookies Secure y operación distribuida. No se implementan rastreo, IA, favoritos ni notificaciones.
