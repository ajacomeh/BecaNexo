# Integración continua

El workflow está en `.github/workflows/ci.yml` y tiene tres jobs:

- **Detectar cambios** (`cambios`): un job liviano que decide qué verificaciones necesita cada PR.
- **Backend:** corre en Windows con PostgreSQL 16. Ejecuta `check`, `makemigrations --check` y las pruebas.
- **Frontend:** corre en Ubuntu con Node 24. Ejecuta lint, Vitest y build.

## Cuándo se ejecuta

- **`pull_request` sobre `main`:** valida cada PR una sola vez por subida. Si llega una subida nueva al mismo PR, se cancela la ejecución anterior.
- **`push` a `main`:** hace siempre la verificación completa tras cada merge. Estas ejecuciones nunca se cancelan.
- **`workflow_dispatch`:** lanza manualmente la verificación completa.

## Ejecución selectiva en los PR

El job `cambios` compara la base del PR con su cabeza (`git diff --name-only base...cabeza`) y clasifica cada archivo:

| Archivos cambiados | Backend | Frontend |
|---|---|---|
| Solo `docs/**` o `*.md` | omitido | omitido |
| `frontend/**` | — | se ejecuta |
| `backend/**` (incluidas las migraciones y `requirements*`), `.python-version`, `pyproject.toml`, `setup.cfg` o `*.sql` | se ejecuta | — |
| `.github/workflows/**` | se ejecuta | se ejecuta |
| Cualquier otra ruta | se ejecuta | se ejecuta |

Reglas de seguridad:

- En `push` a `main` y en `workflow_dispatch` se ejecutan siempre los dos jobs.
- También se ejecutan los dos si el diff no se puede calcular, si está vacío o si el propio job `cambios` falla.
- Un job omitido aparece como «skipped», no como fallo.

## Límites y cachés

- **Tiempo máximo por job:** 5 minutos para «Detectar cambios», 40 para el backend y 20 para el frontend (`timeout-minutes`).
- **Cachés:** pip (`backend/requirements.txt`), npm (`frontend/package-lock.json`) y el modelo semántico ONNX (`actions/cache`).
- **Configuración del backend:** usa `config.settings_ci`, sin secretos reales.
