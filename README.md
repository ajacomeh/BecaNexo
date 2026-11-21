# BecaNexo

BecaNexo es un proyecto de tesis de Ingeniería de Software para consultar y recomendar becas a ciudadanos ecuatorianos. Registra únicamente ofertas de entidades ecuatorianas; el destino de estudio puede estar en Ecuador o en otro país. La aplicación **no tramita postulaciones ni adjudica becas**: el postulante debe consultar las bases y postular en el sitio oficial de la entidad oferente.

## Estado del proyecto

- Implementado: cuentas con correo, sesiones y CSRF; perfil académico; catálogo, detalle, filtros y favoritos; administración de convocatorias; comparación explicable de requisitos agrupada por resultado; recomendaciones con un modelo semántico local; notificaciones internas y correo con consentimiento.
- Rastreo real: SIAU, con captura manual desde el panel de rastreo y corrida programada diaria. Cada ficha en alcance genera un borrador privado con llenado automático; el administrador lo revisa y lo publica con «Validar y publicar». **Ninguna convocatoria se publica automáticamente**.
- En prueba aislada: conectores UTPL, UPS y portal institucional genérico, y una demostración multifuente con HTTP, HTML y PDF sintéticos. Su existencia en el código no acredita acceso autorizado ni funcionamiento operativo con esos sitios.
- Pendiente: verificar condiciones de acceso y conservación para fuentes adicionales, ampliar la validación con fichas reales autorizadas y medir la calidad de las recomendaciones. La descarga PDF individual está desactivada por defecto.

La versión `0.1.0` de `frontend/package.json` identifica el paquete frontend; el proyecto completo aún no tiene una versión de lanzamiento oficial.

## Flujo de trabajo

### Rastreo de SIAU

- **Captura manual**: en el panel de rastreo del administrador, «Iniciar rastreo» pide un motivo de al menos 10 caracteres y solo está disponible cuando una fuente autorizada ya admite captura por su frecuencia y no hay otra ejecución activa.
- **Corrida programada**: la tarea de Windows `BecaNexo-Rastreo-SIAU` se dispara cada hora y ejecuta `scripts/rastreo-programado.ps1 -Ejecutar`. Solo captura cuando venció la ventana de la fuente (`frecuencia_min` = 1440, es decir, 24 horas); antes responde «no corresponde aún» sin hacer peticiones a SIAU.
- **Modos del script**: `-Comprobar` (solo lectura: estado de la programación de la fuente), `-Ejecutar` (lo que lanza la tarea) y `-Revisar` (solo lectura: últimas corridas programadas, si la captura está atrasada más de 2 horas respecto de la hora prevista y el final del registro local).
- **Corridas interrumpidas**: una corrida programada que quedó «en curso» sin latido en los últimos 10 minutos (por ejemplo, por un apagado del equipo) se cierra automáticamente como fallida, con la incidencia `INTERRUMPIDA`, antes de la siguiente. La corrida cerrada sigue consumiendo la ventana de 24 horas.
- **Resumen**: cada corrida programada registra un resumen legible (peticiones, publicaciones observadas, versiones nuevas, candidatos nuevos, borradores creados e incidencias) en `%LOCALAPPDATA%\BecaNexo\rastreo\programador.jsonl`. Ver [comandos de rastreo](docs/comandos-rastreo.md).

### Borrador privado automático

Con `RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS` activo, cada ficha en alcance crea un borrador privado (revisión pendiente, fuera del catálogo). El llenado automático escribe en sus campos y en las listas de requisitos, beneficios y opciones de estudio solo lo que la ficha y las bases en PDF dicen con claridad; lo ambiguo queda como evidencia. Los requisitos se crean sin validar y nunca se sobrescribe lo que el administrador ya editó o vació. De las bases en PDF se toman requisitos, beneficios con importe o porcentaje y obligaciones de la persona becaria. La entidad oferente se asigna cuando la ficha o las bases nombran a una entidad ecuatoriana como oferente, o como la que adjudica o firma el contrato de financiamiento; si no está registrada, se crea con país Ecuador. El comando `completar_borradores` aplica el mismo llenado a borradores existentes.

### Publicación en un clic

«Validar y publicar» comprueba la entidad oferente ecuatoriana, el título, la descripción, el enlace oficial, al menos una opción activa, el contrato de cada requisito, las condiciones comunes duplicadas y los beneficios superpuestos. En la misma operación valida los requisitos activos pendientes y registra el evento de auditoría `confirmar_publicacion` a nombre de quien publica. La primera publicación genera los avisos a los postulantes compatibles.

### Requisitos y comparación

Tipos de requisito: Nacionalidad, Estudios mínimos, Título y área, Edad, Promedio y escala, Idioma y nivel, Experiencia, Dedicación, Disponibilidad de traslado, Residencia, Certificación externa, Documento externo, Otra condición externa y Condición administrativa. La tipificación es estricta: un tipo estructurado solo se usa cuando el texto escribe sus valores; las condiciones que la entidad oferente comprueba en sus registros (becas vigentes, otros programas, sanciones, títulos registrados) son «Condición administrativa», las demás condiciones sin valores son «Otra condición externa» y los documentos son «Documento externo». Los tipos externos nunca dan «cumple» por sí solos. El comando `retipificar_requisitos` vuelve a tipificar los requisitos del llenado con estas reglas.

En el detalle de una beca, el postulante ve sus requisitos agrupados en «No cumples», «Por confirmar» y «Cumplidos», según los datos que declaró.

### Avisos

Al publicar, los postulantes compatibles reciben un aviso interno. El correo es opcional: requiere el consentimiento del postulante, `AVISOS_CORREO_HABILITADOS` y la configuración Gmail; la tarea de Windows `BecaNexo-Notificaciones-Gmail` (`scripts/correo-programado.ps1`) procesa la cola cada cinco minutos. Ver [correo](docs/correo-gmail.md).

## Tecnologías y estructura

| Ruta | Función |
| --- | --- |
| `backend/usuarios`, `backend/perfiles` | Cuentas, autenticación, datos académicos y preferencias |
| `backend/convocatorias`, `backend/favoritos` | Becas, requisitos, comparación, recomendaciones y favoritos |
| `backend/rastreo` | Fuentes, ejecuciones, evidencias, candidatos, propuestas y borradores |
| `backend/notificaciones` | Avisos internos, consentimiento y cola de correo |
| `frontend/src` | Interfaz React con Vite y Tailwind CSS |
| `scripts/` | Automatización local y demostraciones aisladas |

Backend: Python 3.13, Django 5.2, Django REST Framework y PostgreSQL 16. Frontend: React 19, Vite 8, Tailwind CSS 4 y **Node.js 24** (`>=24 <25`). La afinidad temática usa ONNX Runtime en CPU con el modelo preentrenado `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Sus vectores sirven para ordenar por similitud; no son probabilidades de adjudicación ni sustituyen las reglas explícitas de requisitos.

## Instalación local en Windows

Se requiere Python 3.13, PostgreSQL 16 y Node.js 24. Trabaja desde la raíz del repositorio en PowerShell. Crea una base y un usuario PostgreSQL **locales** para esta instalación; no copies la base de desarrollo de otra persona.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Edita `backend/.env` **solo en tu equipo** para configurar una clave secreta propia, la conexión PostgreSQL y los hosts locales. No subas ese archivo ni compartas sus valores. **Solo para una base nueva y vacía**, tras verificar el destino configurado, prepara esquema y catálogos:

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate --noinput
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos_convocatorias
```

Consulta [la guía local](docs/ejecucion-local.md) para los recorridos de prueba. Para la afinidad ONNX, descarga los archivos fijados y comprobados por el proyecto:

```powershell
.\.venv\Scripts\python.exe backend\scripts\download_semantic_model.py
```

El modelo queda en `.local-models/`, excluido de Git. La aplicación conserva la comparación de requisitos si el modelo no está disponible. No son necesarias credenciales Gmail para arrancar; sin ellas se utiliza el backend de consola y los avisos por correo están desactivados por defecto.

Inicia backend y frontend en terminales separadas:

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Abre `http://127.0.0.1:5173/`. Usa el mismo host `127.0.0.1` en ambos servicios para conservar las cookies y CSRF. `npm.cmd` evita depender de la política de ejecución de `npm.ps1` en PowerShell.

## Comprobaciones y demostración

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
```

Las pruebas backend usan una base de pruebas separada; las de frontend están en `frontend/src` y `frontend/e2e`. Consulta [ejecución local](docs/ejecucion-local.md) antes de ejecutar pruebas E2E, porque algunos recorridos históricos escriben datos de demostración en la base configurada. La [demostración multifuente](scripts/demo-multifuente-visual.ps1) utiliza `test_becanexo_fusion_db`, puertos 8001/5174 y correo en memoria; no representa una consulta institucional real.

## Seguridad y alcance operativo

`backend/.env`, `.venv/`, `.local-models/`, `outputs/rastreo/`, `frontend/node_modules/`, `frontend/dist/`, registros y respaldos locales están excluidos por `.gitignore`. El repositorio no contiene las cuentas, convocatorias ni documentos de la base local. La configuración Gmail y las tareas Windows son opcionales y requieren habilitación explícita; publicar una convocatoria puede generar avisos internos y, con consentimiento y compatibilidad confirmada, entregas de correo.

El rastreo respeta la política y frecuencia de cada fuente, robots, límites HTTP, bloqueos 429/503 y `Retry-After`. El acceso público a una página o un `robots.txt` permisivo no equivalen por sí solos a autorización para capturar y conservar sus contenidos. La documentación técnica está en `docs/`, en particular [rastreo](docs/comandos-rastreo.md), [recomendación](docs/recomendacion-semantica.md) y [correo](docs/correo-gmail.md).

No hay todavía un archivo de licencia para redistribución del proyecto; conviene decidirlo antes de publicar el repositorio.

## Alcance y trabajo futuro

Quedan fuera del alcance de esta versión:

- Alertas de cambio de formato de la fuente rastreada.
- Control de duplicados entre fuentes (misma beca con el mismo título y cierre en dos fuentes); hoy solo se rastrea SIAU.
- Publicación masiva de convocatorias.
- Avisos al postulante cuando cambia su perfil.
- Avisos internos para el administrador.
- Extracción visual de tablas en las bases.
- Más fuentes institucionales además de SIAU.
- El disparador de inicio de sesión de la tarea programada puede lanzar la corrida justo al reanudar el equipo.
- Una corrida programada interrumpida cuenta como captura de la ventana de 24 horas.
- La tarea programada solo corre con la sesión de Windows abierta y el equipo despierto, o al recuperar disparos perdidos con `StartWhenAvailable`.
