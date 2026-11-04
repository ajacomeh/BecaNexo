# Perfil del postulante

Implementado el 25 de octubre de 2026 a partir del modelo lógico v0.5, Diccionario.md, Reglas_y_requisitos.md y las pantallas 6 y 7 del PDF. Usa la app `perfiles` dentro del monolito modular. No implementa convocatorias, cálculo de elegibilidad, IA, rastreo o notificaciones.

## Permisos y seguridad

Todas las rutas requieren sesión Django; las operaciones de autoservicio exigen `rol=postulante`. Administradores autenticados pueden leer catálogos, pero no gestionar un perfil por estas rutas. Los propietarios se obtienen de request.user; jamás de un dato enviado por el cliente. En las relaciones, las consultas por ID incluyen el propietario y producen el mismo 404 para un registro ajeno o inexistente.

Se reutiliza la autenticación con CSRF explícito de usuarios. POST, PATCH y DELETE necesitan cookie y X-CSRFToken. Las respuestas no se almacenan en caché. No se exponen usuario_id, hashes ni privilegios. Campos no permitidos, incluidos id, perfil_id, usuario_id, rol, version y actualizado_en en escrituras, producen 400. El nombre visible permanece en MAE_USUARIO y se muestra sin editar desde este módulo: no se duplica ni se modifica el rol.

## Endpoints

Todos tienen prefijo `/api/perfil/`, barra final y cuerpos JSON.

| Ruta | Métodos | Comportamiento |
|---|---|---|
| `/api/perfil/` | GET | 200 con `{"perfil": null}` si todavía no existe; leer no crea registros |
| `/api/perfil/` | PATCH | Crea perfil propio progresivo (201) o actualiza el existente (200); devuelve `{"perfil": {...}}` |
| `catalogos/` | GET | 200: paises, idiomas, areas y dominios de selección |
| `formaciones/` | GET, POST | Lista propia (200), crear (201) |
| `experiencias/` | GET, POST | Lista propia (200), crear (201) |
| `idiomas/` | GET, POST | Lista propia (200), crear (201) |
| `areas/` | GET, POST | Lista propia (200), crear (201) |
| `preferencias/` | GET, POST | Lista propia (200), crear (201) |
| `destinos/` | GET, POST | Lista propia (200), crear (201) |
| Cada colección anterior + `<id>/` | GET, PATCH, DELETE | Leer (200), editar parcialmente (200), eliminar sin cuerpo (204) |

Las listas vacías devuelven `[]`, no cero experiencia ni una conclusión de elegibilidad. DELETE admite cuerpo vacío o `{}`; rechaza campos. OPTIONS está disponible. Métodos no habilitados producen 405 después de permisos/CSRF; 403 para sesión ausente, rol no permitido o CSRF; 404 para IDs ajenos/inexistentes; 400 para validación y duplicados; 409 al intentar crear una relación antes de guardar el perfil; 503 si falta el catálogo Ecuador al crear el perfil. Los errores de formato JSON/tipo de contenido siguen el contrato DRF (400/415).

No hay endpoints públicos de escritura de catálogos. Los IDs de países, áreas e idiomas se obtienen de catalogos/, nunca deben fijarse en el frontend. Los selectores de dominio incluyen `valor` y `nombre`; los catálogos incluyen `id`, `nombre` y `codigo` cuando el ER lo contempla.

## Campos de entrada

- Perfil: descripcion, nacionalidad, residencia, fecha_nacimiento, provincia_residencia, ciudad_residencia, dedicacion_disponible, disponible_traslado, disponible_extranjero. Nacionalidad debe declararse al crear y su código debe ser EC; PATCH sobre perfil existente conserva la guardada si se omite. No se asigna Ecuador automáticamente. La residencia puede ser cualquier entrada del catálogo o NULL. Nacionalidad no significa residencia.
- Formación: nivel, carrera, institucion, titulo_obtenido, promedio, escala_min, escala_max, estado_estudios, nombre_titulo, fecha_finalizacion, area. Obligatorios al crear: nivel, carrera, titulo_obtenido y estado_estudios. No se sustituye una respuesta desconocida al título por False: la fila se crea cuando se declara ese dato obligatorio.
- Experiencia: area, cargo, descripcion, fecha_inicio, fecha_fin, actual. Obligatorios: fecha_inicio y actual.
- Idioma: idioma (ID obligatorio), nivel opcional. No hay certificados, archivos o fechas de certificación.
- Área de interés: area (ID obligatorio).
- Preferencia: nivel y modalidad obligatorios, una combinación por fila.
- Destino: pais (ID obligatorio).

Los campos FK usan estos nombres sin sufijo `_id` en la API, con un entero como valor. En PostgreSQL las columnas son nacionalidad_id, residencia_id, perfil_id, area_id, idioma_id y pais_id según el ER. Fechas: YYYY-MM-DD. Decimales: hasta 7 dígitos totales y 3 decimales; DRF los representa como cadenas en respuestas para evitar pérdida de precisión. Booleanos: true/false, y null únicamente donde el modelo admite desconocido.

Ejemplo de actualización de un perfil existente, después de obtener CSRF:

```json
{
  "ciudad_residencia": "Quito",
  "disponible_traslado": false,
  "disponible_extranjero": null
}
```

PATCH solo cambia los campos enviados. Vacíos opcionales (incluso espacios) se normalizan a NULL; false y 0 se conservan. El frontend envía los campos del formulario de su sección, por lo que guardar datos personales no cambia disponibilidad ni viceversa.

## Descripción opcional del perfil (04/11/2026)

`descripcion` pertenece a `MAE_PERFIL`, no a la cuenta ni a una experiencia laboral. Es un campo nuevo respecto al modelo base v0.6: texto nullable, máximo 1500 caracteres validado por el serializer. GET lo incluye; PATCH acepta texto, `null`, `""` o espacios para borrarlo (normalizados a NULL). Omitirlo conserva su valor; superar el límite devuelve 400 sin guardar. Ejemplo: `{"descripcion": "Intereses académicos y objetivos de estudio"}`. No se interpreta HTML ni se usa en comparación, afinidad o IA. Conserva sesión, CSRF y propietario derivado de request.user.

La interfaz lo presenta como «Sobre mi perfil», con contador y ayuda sobre datos sensibles. No precarga contenido. La migración aditiva `perfiles.0002_perfil_descripcion` añade la columna nullable sin descripciones ficticias; se probó en `test_becanexo_db` y se dejó sin aplicar en desarrollo. Antes de usar la nueva versión del perfil en desarrollo, aplicar expresamente desde la raíz:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate perfiles 0002_perfil_descripcion
```

Este comando no se ejecutó sobre desarrollo durante la implementación. Hasta aplicarlo, el código actualizado de perfil requiere una columna que todavía no existe en esa base.

## Validaciones e integridad

- Un perfil por usuario: OneToOne y restricción única de PostgreSQL. FK válidas en todas las relaciones. Nacionalidad EC se valida en el servidor; no se hardcodea el ID de Ecuador.
- Fecha de nacimiento no futura. Formación: un título obtenido requiere estudios concluidos; no se admite fecha final para estudios en curso ni una fecha final futura. Carrera no vacía.
- Promedio y sus dos extremos se declaran juntos o quedan todos NULL. Mínimo estrictamente menor al máximo y promedio dentro del intervalo, incluidos extremos. No se convierte a una escala nueva ni se interpreta un promedio vacío como 0.
- Experiencia actual exige fecha_fin NULL; experiencia finalizada exige fecha_fin y fin >= inicio. Inicio y fin no pueden ser futuros. No se suman periodos ni se interpreta ausencia como cero meses.
- Niveles académicos: bachillerato, grado, especializacion, maestria, doctorado. Estados: en_curso/concluidos. Dedicación: completa/parcial/ambas o NULL. Idiomas: A1–C2 o NULL. Modalidades de esta entrega: presencial/virtual/semipresencial.
- Unicidad en perfil+idioma, perfil+área, perfil+país y perfil+nivel+modalidad. Conflictos de unicidad se capturan fuera del bloque atómico y devuelven 400 junto al campo; no se exponen mensajes SQL.
- PostgreSQL comprueba dominios, carrera no vacía, escalas/promedio, coherencia título/estado, fechas de estudios en curso, periodos de experiencia, unicidades y FK. Fechas respecto de «hoy» y nacionalidad EC se validan en la API; no se crean CHECK dependientes de otra tabla o del paso del tiempo.

## Versionado y transacciones

La creación comienza en version=1. Cada PATCH aceptado del perfil y cada alta, edición o eliminación de una relación incrementan version una vez y actualizan actualizado_en dentro de la misma transacción. Esto incluye guardados sin diferencias: version cuenta escrituras aceptadas, no calcula un diff semántico. Las peticiones rechazadas y sus errores no cambian la versión.

Todas las escrituras bloquean la fila MAE_USUARIO del propietario con select_for_update. Esto serializa incluso dos creaciones cuando aún no existe MAE_PERFIL; los incrementos usan F. Hay pruebas de rollback y de dos escrituras concurrentes con conexiones independientes a test_becanexo_db. El ejecutor de pruebas no usa --parallel.

No hay señales globales ni escritura de perfiles desde Django Admin. Futuras tareas que escriban por ORM, SQL o una nueva interfaz deberán pasar por el mismo mecanismo transaccional de versionado. No se implementa control optimista de versiones del cliente: si se edita el mismo campo desde dos pestañas, prevalece el último guardado. Esta versión tampoco es una instantánea histórica suficiente para reproducir futuras recomendaciones.

## Mapeo y ajustes documentados

Se crean exactamente las diez tablas del alcance: MAE_PERFIL, MAE_FORMACION, MAE_EXPERIENCIA, CAT_PAIS, CAT_IDIOMA, CAT_AREA, REL_PERFIL_IDIOMA, REL_PERFIL_AREA, CFG_PREFERENCIA y REL_PERFIL_PAIS. No se añaden columnas de negocio, catálogos de nivel/modalidad ni tablas de certificados. BigAutoField implementa los IDs bigint; PositiveIntegerField y CHECK >=1 implementan version; timestamps usan zona horaria. CAT_PAIS.codigo es varchar(2) con CHECK de dos mayúsculas, en lugar del char(2) lógico, para evitar relleno de espacios.

El modelo no enumera las modalidades: se concretó el dominio presencial/virtual/semipresencial sin crear una tabla adicional. «Presencial o virtual» en el prototipo se representa con dos filas, no un valor ambiguo. Las áreas iniciales son las 11 categorías amplias de CINE-F, no todas las especialidades ilustrativas del PDF. Idiomas tiene cobertura inicial de 12 entradas. Fuentes y cobertura: `backend/perfiles/data/FUENTES.md`.

Los campos opcionales permanecen NULL. No se crean automáticamente formaciones o experiencias incompletas: la edición progresiva se realiza guardando cada sección/registro válido. El botón de guardado pertenece a cada sección para que un error en otra no elimine avances. El nombre del usuario es solo lectura en estas pantallas.

## Migración y carga

Antes de aplicar se comprobó que perfiles no tenía migraciones aplicadas, que las diez tablas no existían y que 0001_initial solo contiene CreateModel y AddConstraint. Después de aprobar backend/frontend se ejecutó en becanexo_db:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate perfiles --noinput
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos
```

Estado confirmado: perfiles.0001_initial aplicada. La carga se ejecutó dos veces: 249 países/territorios, 12 idiomas y 11 áreas, sin duplicados. Es aditiva; no reconstruye la base, no elimina datos ni modifica credenciales o el administrador.

## Comprobación manual

1. Iniciar backend y frontend como indica ejecucion-local.md; iniciar sesión como postulante y abrir «Completar mi perfil» desde /inicio.
2. En /perfil, declarar residencia y datos opcionales; guardar datos personales. Probar residencia en España y nacionalidad fija Ecuador. Recargar y comprobar persistencia.
3. Añadir una formación con nivel, carrera, estado y respuesta explícita sobre el título. Declarar un promedio con escala, provocar uno fuera de rango, corregir y guardar. Editar la fila guardada.
4. Añadir experiencia con inicio y respuesta explícita sobre si continúa. Para finalizarla, indicar fecha final. Probar eliminar, cancelar y luego confirmar la eliminación del registro de prueba.
5. En /preferencias, añadir idioma/nivel. Repetir idioma y comprobar el error. No cargar documentos: los certificados los verifica la entidad oferente.
6. Añadir combinaciones nivel/modalidad, áreas y países. Guardar disponibilidad con «No» en traslado y «Sin declarar» en extranjero; recargar y comprobar que siguen siendo distintos.
7. Simular una desconexión al guardar: se muestra error, los campos siguen escritos y no aparece confirmación de guardado. Reconectar y reintentar.
8. Con administrador, /inicio no invita a completar perfil y /perfil redirige a inicio; la API devuelve 403 si se intenta gestionar un perfil con ese rol.

Las pruebas automatizadas están en perfiles/tests.py, frontend/src/Profile.test.jsx y frontend/e2e/profile.spec.js. El recorrido de navegador usa una cuenta desechable nueva, no mocks. Registra, inicia sesión, crea perfil, edita formación, crea y elimina una experiencia de prueba con confirmación, guarda idioma/preferencias/área/destino/disponibilidad, recarga, comprueba persistencia y cierra sesión. No toca cuentas existentes. Las capturas se guardan solo en test-results, excluido de Git.
