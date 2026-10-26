# Guía de demostración para la revisión de avances

## Preparación local

Desde `D:\Proyectos\BecaNexo`, en PowerShell:

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py cargar_demo_avances --vista-previa
```

La vista previa no escribe, ni siquiera para luego revertir. Si ya existe la carga completa, comprueba su integridad y ejecuta nuevamente el comparador. En esta instalación se utiliza el administrador existente ID 8 como autor de la carga por consola y de la auditoría; no se cambia su cuenta. Para una instalación distinta debe indicarse el ID de un administrador activo propio.

```powershell
.\.venv\Scripts\python.exe backend/manage.py cargar_demo_avances --aplicar --actor-id 8
```

El comando no crea catálogos, no cambia contratos, no migra y no contacta con example.org. Requiere catálogos y migraciones existentes. Usa una transacción, validadores de los serializers, publicación por el servicio vigente y AUD_EVENTO. Un lock transaccional de PostgreSQL serializa cargas concurrentes de esta demostración. Si encuentra una carga parcial, colisión, datos cambiados o definición del fixture distinta, se detiene sin sobrescribir. No hay opción de borrado ni de forzar actualización.

## Cuenta de acceso

Correo exacto: **revision-avances@example.com**. Nombre visible: **DEMOSTRACIÓN · Persona sintética de revisión**. Rol postulante activo, sin acceso administrativo ni privilegios elevados. La carga inicial crea una contraseña inutilizable, no una contraseña conocida o vacía.

Establecer la contraseña localmente mediante entrada oculta de Django:

```powershell
.\.venv\Scripts\python.exe backend/manage.py changepassword revision-avances@example.com
```

Introducir y confirmar una contraseña que supere los validadores. No escribirla en argumentos, documentación ni mensajes. Este comando solo afecta a la cuenta indicada. La carga no lee ni compara contraseña/hash ni last_login para decidir idempotencia: cambiar contraseña e iniciar/cerrar sesión no impide reutilizarla. Cambiar el perfil o las ofertas sí provoca una diferencia que requiere revisión manual; no se restauran automáticamente.

## Arranque y recorrido

Terminal 1, raíz del proyecto:

```powershell
$env:DJANGO_CSRF_TRUSTED_ORIGINS = 'http://127.0.0.1:5173'
.\.venv\Scripts\python.exe backend/manage.py runserver 127.0.0.1:8000
```

Terminal 2, raíz del proyecto:

```powershell
$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
Set-Location frontend
npm.cmd run dev
```

Abrir http://127.0.0.1:5173/ y explorar `/becas` sin sesión. Buscar «REVISIÓN DE AVANCES». Todas las entidades, instituciones de destino y enlaces de estas cinco ofertas son ficticios. No son convocatorias reales ni representan convenios.

1. Mostrar catálogo compacto y detalle público: beneficios por concepto, destinos, opciones y documentos externos. No abrir los enlaces ficticios como si fueran bases reales.
2. Iniciar sesión en `/login` con la cuenta sintética. Mostrar `/perfil` y `/preferencias` sin guardar cambios.
3. Recorrer A, B, C, D y E; en cada detalle pulsar **Comparar requisitos**. No se ejecuta una solicitud externa de beca.
4. En A explicar que «coincide» significa coincidencia de datos declarados: los documentos siguen pendientes de la entidad oferente.
5. En B revisar inglés C1 frente al B2 declarado; en C el grupo de educación pendiente; en D las tres opciones dentro de una sola convocatoria; en E la imposibilidad de combinar promedios y áreas de formaciones distintas.
6. Opcionalmente guardar y quitar un favorito, recargar y cerrar sesión. Los favoritos no forman parte de la huella del fixture. El visitante conserva acceso al catálogo, pero no al perfil ni a la comparación personal.

## Datos y resultados previstos

El perfil sintético declara ciudadanía ecuatoriana, residencia Quito/Pichincha/Ecuador, nacimiento 15/06/1996 (30 años a 05/11/2026), inglés B2, dedicación ambas y disponibilidad de traslado nacional/extranjero. Hay tres grados concluidos con título y áreas de catálogo explícitas:

| Formación | Área | Promedio | Escala |
| --- | --- | --- | --- |
| Ingeniería de Software | Tecnologías de la información y la comunicación | 7 | 0–10 |
| Administración de Empresas | Administración de empresas y derecho | 9 | 0–10 |
| Educación | Educación | No declarado | Extremos no declarados |

Educación no tiene promedio ni extremos porque el CHECK existente exige declararlos juntos o dejar los tres nulos. Las bases ficticias exigen 8 en escala 0–10, pero no se afirma que el postulante haya declarado esa escala. El grupo área Educación + grado concluido + promedio queda desconocido; los otros dos promedios no resuelven ese grupo. No hay reglas de experiencia en estos escenarios, por lo que no se inventan empleos para llenar el perfil.

Todos los títulos empiezan por **DEMOSTRACIÓN · REVISIÓN DE AVANCES ·**:

En esta instalación, carga confirmada el 26/10/2026:

- [A · Coincidencia declarada](http://127.0.0.1:5173/becas/4).
- [B · Inglés C1 requerido](http://127.0.0.1:5173/becas/5).
- [C · Promedio de educación pendiente](http://127.0.0.1:5173/becas/6).
- [D · Tres alternativas de estudio](http://127.0.0.1:5173/becas/7).
- [E · Área TIC y promedio en la misma formación](http://127.0.0.1:5173/becas/8).

Los IDs son locales; en otra base se obtienen de la salida del comando. Cuenta creada ID 13, sin contraseña utilizable. Creados cinco registros de convocatoria, siete opciones, doce beneficios, cuarenta y cinco requisitos, un oferente ficticio y doce eventos (uno del oferente, cinco de creación, cinco de publicación y uno de huella). El perfil incluye tres formaciones, un idioma, tres áreas de interés, dos destinos preferidos y una preferencia nivel/modalidad. Catálogos y administrador actor ID 8 reutilizados sin cambios.

En esta instalación, carga confirmada el 26/10/2026:

- [A · Coincidencia declarada](http://127.0.0.1:5173/becas/4).
- [B · Inglés C1 requerido](http://127.0.0.1:5173/becas/5).
- [C · Promedio de educación pendiente](http://127.0.0.1:5173/becas/6).
- [D · Tres alternativas de estudio](http://127.0.0.1:5173/becas/7).
- [E · Área TIC y promedio en la misma formación](http://127.0.0.1:5173/becas/8).

Los IDs son locales; en otra base se obtienen de la salida del comando. Cuenta creada ID 13, sin contraseña utilizable. Creados cinco registros de convocatoria, siete opciones, doce beneficios, cuarenta y cinco requisitos, un oferente ficticio y doce eventos (uno del oferente, cinco de creación, cinco de publicación y uno de huella). El perfil incluye tres formaciones, un idioma, tres áreas de interés, dos destinos preferidos y una preferencia nivel/modalidad. Catálogos y administrador actor ID 8 reutilizados sin cambios.

| Caso y sufijo del título | Comparación esperada |
| --- | --- |
| A · Coincidencia declarada | Cumple según datos declarados; certificaciones externas pendientes. |
| B · Inglés C1 requerido | No cumple: B2 declarado no alcanza C1. |
| C · Promedio de educación pendiente | Desconocido: falta promedio de la formación en Educación. |
| D · Tres alternativas de estudio | D1 virtual cumple; D2 presencial incumple C1; D3 semipresencial queda pendiente por Educación. D1 tiene Ecuador y España como alternativas; no se infiere traslado por ese hecho. |
| E · Área TIC y promedio en la misma formación | No cumple: TIC tiene 7 y se exige 8; Administración tiene 9 pero área distinta. Educación también tiene área distinta, de modo que su promedio ausente no convierte este incumplimiento en pendiente. |

El modelo actual no tiene FK de área por opción: los campos de áreas están en la convocatoria y las condiciones académicas de área se expresan en requisitos por opción. El programa describe la temática de cada opción. No se añadió ninguna relación nueva.

## Fechas y contenido ficticio

- Publicación: 19/10/2026. Apertura: 20/10/2026 a las 09:00. Cierre: 30/11/2026 a las 23:59, Ecuador continental (UTC−05:00).
- Abiertas durante la reunión hasta el 05/11/2026. Referencia fija de edad: 05/11/2026, límites 18–40 años inclusivos.
- Inicio académico: 01/03/2027; duración 18 meses; 12 cupos ficticios por opción.
- Apoyo común: 120 USD una sola vez para materiales. Cobertura de matrícula específica: 80 % en opciones únicas y D1, 60 % en D2, 50 % en D3. Porcentaje sin monto fijo ni moneda/periodicidad artificiales; no se suman porcentajes ni se presentan como cobertura total.
- No cubre transporte, alojamiento, seguros ni saldo de matrícula. Obligaciones ficticias: mantener matrícula e informe académico semestral. Certificaciones y expedientes se verificarían externamente; no se cargan archivos ni se crean certificados válidos.
- No se alteran fechas de demostraciones anteriores. Tras el cierre fijo las ofertas pasarán a cerradas según la lógica existente; no se actualizan fechas automáticamente para mantener una apariencia de vigencia.

## Arquitectura, acceso y límites

Django 5.2/DRF es un monolito modular con usuarios, perfiles, convocatorias y favoritos; React/Vite consume la API local, PostgreSQL conserva datos. Usuario tiene un perfil con varias formaciones/idiomas/preferencias. Convocatoria pertenece al oferente, tiene opciones con países y beneficios/requisitos comunes o específicos. Los grupos académicos exigen satisfacer todas sus condiciones con una sola formación.

Sesiones nativas y CSRF protegen escrituras; permisos se verifican en servidor. El perfil y la comparación usan el propietario autenticado. El catálogo público excluye borradores y pausadas incluso por ID. Publicar revalida reglas y registra auditoría; no se inventan ejecuciones de rastreo. Los eventos manuales cumplen la relación obligatoria con actor y exactamente una convocatoria o institución.

Implementado: autenticación por correo, perfil y preferencias, catálogo público, detalle, favoritos, administración y comparación explicable de reglas. Pendiente: similitud semántica/IA, rastreo y notificaciones. No hay porcentajes de compatibilidad ni adjudicación interna.

El comparador usa datos declarados, mantiene desconocidos ante ausencias, no convierte escalas con fórmulas arbitrarias ni cuenta meses con convenciones inventadas. Los certificados son siempre externos. La selección de una opción destacada no es ranking por IA. La configuración local HTTP no es despliegue de producción; limitación de intentos en memoria no constituye defensa distribuida.

## Repetición y verificación

La salida de `cargar_demo_avances` contiene los IDs locales y resultados del comparador real. Repetir `--aplicar` con datos intactos devuelve `reutilizada`, sin nuevas publicaciones ni eventos. Las huellas excluyen contraseñas, last_login, sesiones y favoritos. No contienen ni imprimen credenciales. La huella de la definición impide usar una versión cambiada del fixture para sobrescribir datos antiguos.

Pruebas reproducibles, sin paralelismo:

```powershell
.\.venv\Scripts\python.exe backend/manage.py test convocatorias.test_demo_avances --keepdb --verbosity 2
```

Se ejecutan únicamente en `test_becanexo_db`, distinta de `becanexo_db`. Las pruebas HTTP usan APIClient; su autenticación de prueba no constituye un recorrido de navegador con login real. Establecer la contraseña y realizar el recorrido interactivo queda a cargo del presentador; no se ha generado una contraseña ni afirmado una sesión real en navegador.

Resultados reales: 10 pruebas específicas aprobadas (10,607 s) y 121 pruebas de regresión completas aprobadas (78,217 s) con `--keepdb`, sin paralelismo. Django check correcto y makemigrations --check --dry-run sin cambios. Carga de desarrollo ejecutada y repetida: primero `creada`, después `reutilizada`, con resultados A–E comprobados en ambas. APIClient en desarrollo obtuvo 200 y cinco ofertas en catálogo, 200 en los cinco detalles y 200 en las cinco comparaciones con autenticación de prueba en memoria; ninguna sesión real creada para esta comprobación. Huellas de filas previas en 22 tablas de negocio/usuarios coinciden (excluyen password y last_login para no inspeccionar credenciales). No hubo migraciones, borrados ni actualizaciones de cuentas previas.

Resultados reales: 10 pruebas específicas aprobadas (10,607 s) y 121 pruebas de regresión completas aprobadas (78,217 s) con `--keepdb`, sin paralelismo. Django check correcto y makemigrations --check --dry-run sin cambios. Carga de desarrollo ejecutada y repetida: primero `creada`, después `reutilizada`, con resultados A–E comprobados en ambas. APIClient en desarrollo obtuvo 200 y cinco ofertas en catálogo, 200 en los cinco detalles y 200 en las cinco comparaciones con autenticación de prueba en memoria; ninguna sesión real creada para esta comprobación. Huellas de filas previas en 22 tablas de negocio/usuarios coinciden (excluyen password y last_login para no inspeccionar credenciales). No hubo migraciones, borrados ni actualizaciones de cuentas previas.
