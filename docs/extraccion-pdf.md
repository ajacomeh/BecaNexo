# Lectura editorial de PDF archivados

La extracción PDF usa las relaciones `REL_VERSION_DOCUMENTO` con rol `bases_pdf` y los archivos privados ya conservados por SHA-256. No consulta portales, no descarga documentos y no cambia versiones ni convocatorias. `editable_candidates` añade una vista de evidencia a la API administrativa del borrador; ninguna frase se valida como requisito ni se aplica al editor automáticamente.

`pypdf` se ejecuta en un proceso hijo sin Django ni acceso a la base. El proceso principal verifica clave, tamaño y huella antes de abrir el archivo. Límites por consulta: tres documentos únicos, 2 MiB por PDF, doce páginas, 300 KiB de contenido descomprimido y 3000 caracteres por página, 120 fragmentos por documento y cinco segundos por proceso. Los recortes se indican en el panel. Un PDF inválido, protegido, escaneado o sin texto seleccionable permanece pendiente; no se usa OCR. Los errores de un documento no impiden revisar los demás.

Cada fragmento conserva texto literal, categoría o sección visible, tipo sugerido, condición inicial/alternativa/renovación y procedencia (versión, documento, página y URL oficial). Fechas y porcentajes son literales o sugerencias pendientes; nunca se asignan porcentajes fijos por la sola lectura de un PDF. Las categorías se reinician en cada página para evitar trasladar una condición a otra sin encabezado explícito.

Para convertir esta evidencia en campos del borrador hace falta revisión administrativa de cada fragmento, su contexto y la fuente oficial. El PDF original sigue siendo la referencia. La biblioteca se fija en `backend/requirements.txt` y se declara en `backend/requirements.in`.
