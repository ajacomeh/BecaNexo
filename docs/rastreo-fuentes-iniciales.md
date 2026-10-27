# SIAU: investigación y vista previa inicial

Fecha de revisión: **26 de octubre de 2026, Ecuador continental**. Base de trabajo: commit local `69c6f0b`, árbol limpio al empezar. Esta etapa crea archivos de observación, no convocatorias ni fuentes aprobadas. No usa ORM, servicios de publicación, usuarios o sesiones; no cambia el catálogo, datos de reunión, credenciales ni permisos.

## Fuentes inspeccionadas y acceso

| Recurso | Resultado real |
| --- | --- |
| [robots.txt](https://siau.senescyt.gob.ec/robots.txt) | HTTP 200; grupo `*`, prohibición `/wp-admin/`, excepción `/wp-admin/admin-ajax.php`. Las rutas iniciales no están prohibidas. No se accedió al área administrativa ni a esa excepción. |
| [Índice de convocatorias](https://siau.senescyt.gob.ec/convocatorias/) | HTTP 200. Inspección del HTML sin ejecutar JavaScript, sin seguir enlaces de catálogo ni sitemap. |
| [Jóvenes del Nuevo Ecuador 2026](https://siau.senescyt.gob.ec/programa-de-becas-nacionales-jovenes-del-nuevo-ecuador-2026/) | HTTP 200, ficha HTML recuperada. |
| [Bases Jóvenes](https://siau.senescyt.gob.ec/wp-content/uploads/2026/07/bn_aa_jdne2026_bases_rf.pdf) | HTTP 200, PDF de 9 páginas; 410799 bytes en la inspección inicial. |
| [Ecuador Productivo](https://siau.senescyt.gob.ec/programa-de-becas-nacionales-de-posgrado-ecuador-productivo/) | HTTP 200, ficha HTML recuperada. |
| [Bases Ecuador Productivo](https://siau.senescyt.gob.ec/wp-content/uploads/2026/10/bn_4to_nivel_2026_13102026_vf-1.pdf) | HTTP 200, PDF de 10 páginas; 375940 bytes en la inspección inicial. |

La primera conexión directa desde el entorno restringido falló con PermissionError/WinError 10013, sin respuesta HTTP. La ejecución autorizada fuera de esa restricción obtuvo los seis HTTP 200, sin CAPTCHA, autenticación ni elusión de un bloqueo del servidor. Robots no constituye una aprobación de fuente ni una autorización para publicar becas. No se ha verificado una política contractual adicional específica para reutilización masiva; no se hace rastreo masivo.

Primera ejecución completa del comando: `2026-10-27T04:32:08.793284+00:00` a `04:32:19.705352+00:00`, equivalente al 26/10 en Ecuador. Carpeta local `outputs/rastreo/20261027T043208793284Z/`. Resultado: dos fichas, seis respuestas 200, cero incidencias de red, estado `completa_con_revision_manual_pendiente`. Los hashes y tiempos individuales están en cada informe. Una segunda ejecución de cierre se registra en avance.md.

## Reproducción

Desde la raíz en PowerShell, con el entorno ya preparado:

```powershell
.\.venv\Scripts\python.exe backend/manage.py previsualizar_siau
```

No hay opción `--aplicar`, URL arbitraria, cuenta, contraseña ni flag para ignorar robots/TLS. Genera una carpeta nueva con fecha UTC en `outputs/rastreo/`, imprime sus rutas y escribe:

- `informe.txt`: informe legible en texto plano, con texto de ficha, datos, evidencia, ausencias y avisos.
- `informe.json`: contrato de observación versión 1; incluye consultas, huellas, metadatos y trazas de acceso.
- `robots.txt`, `portal.html`, `ficha-*.html` y `base-*.pdf`: evidencia original. No abrir HTML como aplicación confiable ni insertar su marcado en React. El comando no ejecuta scripts, archivos ni enlaces.

Las salidas están ignoradas por Git; las fixtures sintéticas sí se versionan. Ninguna fixture se usa como alternativa si falla una descarga. Cada ejecución genera evidencia nueva sin reemplazar una anterior. Salida 1 mediante CommandError si falla robots, hay incidencias parciales o cambia la estructura esperada; el informe se conserva. Salida 0 significa descarga/extracción terminada **con revisión manual pendiente**, nunca aprobación editorial.

La fecha de consulta es UTC; la referencia de vigencia usa el día de Ecuador continental. Una fecha de cierre sin hora se conserva como día, con hora y zona publicadas nulas; solo se llama vencida si es anterior al día de consulta. No se decide el instante de cierre. No se deduce fecha de publicación del nombre del PDF, metadatos de transporte ni consulta.

## Contrato y límites técnicos

**Aclaración comprobada el 27/10/2026:** en los informes históricos consulta_utc del historial se registraba al admitir el intento, antes de esperar. No mide el inicio HTTP; la separación 04:32:08.803–04:32:09.622 no prueba incumplimiento de pausa. Robots usa el mismo limitador. Ahora se espera después de DNS/preparación y se registran inicio_peticion_utc e inicio_peticion_monotonic inmediatamente antes de invocar request. El primero correlaciona tiempos; el segundo permite comprobar intervalos dentro del proceso. No son captura de paquetes ni limitación distribuida. La marca consulta_utc del resultado de descarga usa el inicio instrumentado; la del historial conserva admisión para no confundir espera con acceso. Los informes antiguos no se reescriben. Una prueba con reloj controlado confirma inicios monotónicos 100 y 102 para robots y portal.

**Extracción siau-html/2:** se añaden menciones académicas con expresión completa, sección, contexto, función y nivel_normalizado nulo. Distingue oferta mencionada, formación previa, incidental y contexto por revisar. No es clasificación semántica universal ni equivalencia académica. El listado niveles_mencionados conserva únicamente expresiones del objetivo identificadas como oferta; no genera opciones. Corrige subcadenas históricas y conserva maestría tecnológica sin reducirla a tercer nivel. El identificador del extractor acompaña los resultados nuevos.

**Reprocesamiento local, sin nueva consulta:** ejecutado sobre las dos fichas de `20261027T043208793284Z`, verificando SHA-256 contra informe y huellas de todos los archivos históricos antes/después. Resultado separado en `outputs/rastreo/reprocesamiento-20261027T104723600572Z/`: Jóvenes → técnico, tecnológico, grado; Productivo → maestrías, especializaciones, maestrías tecnológicas. Contexto institucional y formación previa permanecen separados, sin códigos de catálogo. Se conserva la fecha de referencia histórica; reprocesado_utc no es fecha de descarga. Ninguna fixture sustituyó evidencia real ni se efectuaron peticiones de red. El script auxiliar local ignorado `outputs/rastreo/reprocesar_local.py` permite repetirlo con `.\.venv\Scripts\python.exe -X utf8 outputs/rastreo/reprocesar_local.py`; no es una dependencia del comando de descarga.

La propuesta revisada está en [propuesta-persistencia-rastreo.md](propuesta-persistencia-rastreo.md): once tablas propuestas, no creadas, con nulabilidad, claves, relaciones, restricciones, borrado protegido y bloques de implementación. Las decisiones pendientes de aprobación se distinguen de las reglas ya aprobadas.

- `siau_red.py`: descarga. Lista exacta de seis URLs HTTPS: robots, índice, dos fichas, dos bases conocidas. Las únicas redirecciones posibles son a otra URL de esa lista, de nuevo sometida a robots. Máximo dos redirecciones y dos intentos por salto; solo errores de conexión y 502/503/504 admiten un reintento. 403/404/429 no se eluden ni reintentan. Error TLS se detiene.
- DNS: todas las IP resueltas deben ser públicas, no multicast; rechaza mezclas públicas/privadas. Socket fijado a la IP validada, TLS con hostname y certificados verificados; no proxies heredados, cookies ni credenciales. Se bloquean esquemas alternativos, userinfo, query, fragmentos y otros dominios, incluido PUSAK como destino de descarga.
- Pausa mínima de 2 segundos entre comienzos de petición; se respeta un crawl-delay mayor. Timeout de socket 15 segundos, límite de lectura 45 segundos comprobado entre bloques. No es un plazo estricto de extremo a extremo: DNS depende del sistema y una lectura puede consumir hasta su timeout adicional. Máximo 2 MiB por HTML/robots y 8 MiB por PDF, incluso sin Content-Length; compresión no admitida, tipo MIME y firma PDF comprobados. Máximo dos bases distintas por ejecución, deduplicadas, sin seguir enlaces internos del PDF.
- `siau_extraccion.py`: extracción sin red. HTMLParser, sección de título/contenido con marcador de requisitos; texto de párrafos/listas, notas intercaladas e instrucciones previas a requisitos. Omite scripts/estilos, no los ejecuta. Conserva HTML completo aunque cambie la estructura. No se presenta el parser como soporte universal de WordPress.
- Validación separada: ausencias, estructura, vigencia, moneda, topes y enlaces dudosos. No ejecuta expresiones, IA ni reglas de elegibilidad, ni llama al comparador.
- `siau_bases.py`: **anotaciones humanas parciales**, no extractor PDF. Se adjuntan solo si URL y SHA-256 del PDF descargado coinciden. PDF nuevo/cambiado: revisión manual pendiente y notas anteriores descartadas. Comparación explícita de fecha de cierre y cifras económicas; ambos valores/procedencias permanecen cuando difieren. No se promete detección automática de todas las contradicciones del documento.

## Hallazgos recuperables

| Campo | Jóvenes del Nuevo Ecuador | Ecuador Productivo |
| --- | --- | --- |
| Descripción | Jóvenes 18–29, estudios nacionales de tercer nivel; manutención por un período de 2026 | Posgrado iniciado o por iniciar en 2026, campos priorizados |
| Entidad | Descripción HTML no identifica nominalmente oferente. PDF contiene evidencia MINEDEC, comité y contacto ministerial; registrar atribución solo tras revisión | Objetivo HTML y PDF identifican Ministerio de Educación, Deporte y Cultura – MINEDEC |
| Beneficio | USD 828.97, manutención, una sola vez; no beca del 100 % de todos los costos | 100 % de matrícula y aranceles hasta $3000; exceso a cargo de persona becaria según bases. Moneda ISO pendiente: el símbolo solo no la prueba |
| Estudios | Técnico/tecnológico/grado; todas las modalidades, Ecuador | Especialización, maestría académica y tecnológica; en línea, Ecuador |
| Cierre HTML/PDF | 28/06/2026, coincide; vencida | 25/10/2026, coincide; vencida |
| Apertura observada en PDF | 04/06/2026, p. 4 | 15/10/2026, p. 4 |
| Documentos | Certificado de estudios incluso en sección «Cómo postular»; verificación externa | Admisión, título y otros respaldos detallados en bases; verificación externa |

No se encontraron contradicciones entre las fechas de cierre y cifras económicas cotejadas. Sí hay **diferencias de detalle**: el HTML es un resumen, las bases contienen documentación, condiciones, priorización y obligaciones adicionales. No se certifica una comparación exhaustiva de todas sus cláusulas.

Ambos HTML contienen un enlace POSTULA terminado en `login.` (punto final en el href). Se conserva literalmente, se advierte y no se visita ni corrige silenciosamente. PUSAK es plataforma externa de postulación, no oferente ni fuente autenticada para rastrear.

## Bases: recuperación y revisión pendiente

Los dos PDF tienen capa textual recuperable. La inspección puntual utilizó una herramienta PyMuPDF temporal **ya existente fuera del repositorio**, sin instalar ni añadir dependencia al proyecto. Se inspeccionó texto y se renderizó/revisó visualmente la página 2 de ambos documentos, comprobando la alineación de conceptos, presupuesto y documentos. Las descargas/renders/textos auxiliares permanecen bajo outputs/rastreo ignorado.

El comando guarda el PDF original completo pero **no extrae automáticamente todas sus tablas ni transcribe todos los requisitos PDF al JSON**. Conserva completos los requisitos HTML, incluida la nota de grados superiores de Productivo y el certificado previo a la lista de Jóvenes; las condiciones solo presentes en PDF quedan accesibles en su archivo original, explícitamente pendientes de revisión manual. El alcance solicitado no requiere OCR general; tampoco se pretende que una nota manual sea una extracción dinámica.

Huellas de las versiones inspeccionadas:

- Jóvenes: `f1f52296aa6a5896d02aba2dd731ce49ec04415efe011578af68daea775ec2c3`.
- Productivo: `b04ae4b7dd597bee88b46e7fc8023d1c2adde6b389c8282f79add5a53c004afd`.

Precauciones de interpretación: aprobación del 60 % de malla de Jóvenes corresponde a liquidación, no elegibilidad inicial; escalas de promedio de Productivo corresponden a priorización, no a mínimos generales. Los 39 campos detallados de Productivo necesitan mapeo revisado. Derechos de participación en Ecuador no se transforman automáticamente en una regla de nacionalidad. Incumplimiento de créditos, sanciones, documentos e interoperabilidad se conservan como condiciones externas, sin deducciones a partir del perfil.

## Contraste con modelo lógico v0.6 y Django actual

| Estructura | Reutilizable | Diferencia / decisión previa necesaria |
| --- | --- | --- |
| MAE_INSTITUCION y MAE_CONVOCATORIA | Entidad, título, descripción, enlace, revisión, texto original de cierre, bases | Portal difusor no equivale a oferente. Una institución por convocatoria no representa convenios ni evidencia de participación formal ecuatoriana. No crear oferente ficticio para completar extracción |
| MAE_OPCION_ESTUDIO / REL_OPCION_ESTUDIO_PAIS | Nivel/modalidad y destinos explícitamente asociados | Catálogos actuales no cubren fielmente los niveles técnicos/tecnológicos y todas las modalidades citadas. Unicidad convocatoria+nivel+modalidad puede agrupar programas distintos. No generar producto cartesiano ni colapsar maestría tecnológica por suposición |
| REL_CONVOCATORIA_AREA | Áreas a nivel convocatoria | Campos detallados priorizados no equivalen automáticamente al catálogo actual; no hay relación de área por opción |
| MAE_BENEFICIO | Concepto, porcentaje, monto/moneda, periodicidad, detalle, ámbito común/opción | Falta semántica estructurada separada de tope máximo frente a monto concedido. $3000 no debe insertarse como concesión garantizada; 100 % no significa cobertura total de gastos. El detalle permite conservar texto, no reemplaza decisión de modelado |
| MAE_REQUISITO | Texto, documento, acreditación, referencia, validación y modo externo | Texto libre no se vuelve regla ejecutable. Tipo obligatorio y estructura requieren clasificación revisada; no inventar un tipo para saldar restricciones. Conservar documento íntegro hasta revisión |
| Apertura/cierre | cierre_original y fecha_publicacion nullable | Los DateTimeField no expresan precisión de solo día ni incertidumbre de hora/zona. Mantener observación separada; proponer ampliación/semántica explícita antes de migrar |
| CFG_FUENTE (ER) | URL, identificador de adaptador, límites y activación | Activación no equivale por sí sola a aprobación editorial. Aún no es modelo Django de esta etapa |
| TRA_EJECUCION_RASTREO (ER) | Fuente obligatoria, inicio/fin, estado y contadores | No inventar ejecución ni contadores de publicaciones. Esta ejecución solo queda en archivos, no en tablas |
| TRA_PUBLICACION_FUENTE (ER) | URL normalizada, hash, texto y momentos de observación | convocatoria_id, fuente_id y ejecucion_id son obligatorios. No admite una candidata sin convocatoria canónica; representa última evidencia, no versiones pendientes inmutables. Necesita propuesta previa para observación/candidata y cambios antes de persistir |
| AUD_EVENTO | Auditoría administrativa actual | Implementación exige actor y exactamente convocatoria o institución. Un fallo de red no tiene esos objetos. No usar un usuario ficticio ni omitir restricciones; diseñar incidencia de rastreo ligada a fuente/ejecución |

No se cambió el JSON v0.6, ningún modelo ni migración para resolver estas diferencias.

## Próximo bloque propuesto, todavía no implementado

1. Acordar representación de candidata/observación versionada, evidencia por documento/campo, precisión temporal y tope económico; resolver relación obligatoria de TRA_PUBLICACION_FUENTE sin crear convocatorias artificiales. Presentar modelo y migración antes de implementarlos.
2. Separar fuente activa de fuente aprobada, acreditar oferente y convenios; definir revisión de documentación y mapeos de estudios/áreas con evidencia explícita.
3. Persistir ejecuciones e incidencias de acceso con relaciones válidas. Una desaparición o 403/404 no cancela la convocatoria ni borra favoritos.
4. Proponer cambios respecto a versión publicada, detectar conflictos con correcciones manuales y exigir decisión administrativa. Conservar versión pública hasta aprobación; auditar revisión/publicación con actor real, nunca con una cuenta inventada.
5. Implementar y probar por separado la decisión aprobada de excluir cerradas del conjunto de abiertas por defecto, conservando consulta por filtro y favoritos. La vista previa no modifica esa selección actual.

Pendiente de negocio: precisión/instante de cierre, evidencia de entidad/participación formal, niveles/modalidades nuevos, representación de máximos de financiación, retención de evidencia e incidencias, versión propuesta frente a publicada. No se implementó IA, afinidad, notificaciones, rastreo diario, autenticación PUSAK ni carga de estas dos ofertas.

## Pruebas

```powershell
.\.venv\Scripts\python.exe backend/manage.py check
.\.venv\Scripts\python.exe backend/manage.py test convocatorias.test_siau --keepdb --verbosity 2
```

Se ejecutan secuencialmente, sin paralelismo. Son SimpleTestCase: Django omite la base por no utilizarla y prohíbe toda consulta, incluida la ejecución completa simulada del comando. No se utiliza becanexo_db ni otra base como sustituto de pruebas. La fixture identifica explícitamente contenido ficticio y no se descarga de producción. Cubre datos/evidencia, cierre vencido/ausente/ambiguo, topes, requisitos sin estructurar, documentos, estructura cambiada, hash PDF, conflictos, URL/DNS/redirecciones, HTTP/timeout/TLS, tamaño declarado/streaming, robots fallido y ausencia de escrituras. Resultados finales en avance.md.
