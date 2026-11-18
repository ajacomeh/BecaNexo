# BecaNexo

BecaNexo es un proyecto de tesis de Ingeniería de Software para consultar y recomendar becas a ciudadanos ecuatorianos. Registra únicamente ofertas de entidades ecuatorianas; el destino de estudio puede estar en Ecuador o en otro país. La aplicación **no tramita postulaciones ni adjudica becas**: el postulante debe consultar las bases y postular en el sitio oficial de la entidad oferente.

## Estado del proyecto

- Implementado: cuentas con correo, sesiones y CSRF; perfil académico; catálogo, detalle, filtros y favoritos; administración de convocatorias; comparación explicable de requisitos; recomendaciones con un modelo semántico local; notificaciones internas y correo con consentimiento.
- Rastreo real: SIAU tiene capturas limitadas registradas en el entorno local. Los candidatos, publicaciones detectadas y borradores requieren revisión administrativa; **ninguna convocatoria se publica automáticamente**.
- En prueba aislada: conectores UTPL, UPS y portal institucional genérico, y una demostración multifuente con HTTP, HTML y PDF sintéticos. Su existencia en el código no acredita acceso autorizado ni funcionamiento operativo con esos sitios.
- Pendiente: verificar condiciones de acceso y conservación para fuentes adicionales, ampliar la validación con fichas reales autorizadas y medir la calidad de las recomendaciones. La descarga PDF individual está desactivada por defecto.

La versión `0.1.0` de `frontend/package.json` identifica el paquete frontend; el proyecto completo aún no tiene una versión de lanzamiento oficial.

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
