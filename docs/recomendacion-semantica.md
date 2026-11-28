# Afinidad temática local (bloque 7)

El endpoint `GET /api/becas/recomendaciones/` requiere sesión de postulante activo. Consulta únicamente su perfil y convocatorias públicas. Calcula primero la comparación existente de requisitos para cada convocatoria; agrupa los resultados en `cumple`, `desconocido` y `no_cumple`. Dentro de cada grupo ordena por similitud coseno de embeddings. La afinidad nunca cambia el resultado de elegibilidad ni acredita documentos. No se exponen puntuaciones ni porcentajes: no hay una escala de compatibilidad aprobada. La respuesta conserva `no-store`.

El texto del postulante utiliza áreas de interés, carrera/título/área de formaciones y descripción opcional declarada. El de la convocatoria utiliza título, áreas, programas activos y descripción publicados. Nivel, modalidad y destino preferidos se comparan por igualdad con opciones activas y se explican por separado; no se convierten en requisitos ni en un porcentaje de afinidad total. No se incorporan nacionalidad, correo, edad ni certificados al embedding. Una caché LRU de proceso guarda solo vectores de **texto público de convocatorias**; los textos y vectores personales no se guardan. Para actualizar una representación pública tras una edición basta que cambie el texto; para cambiar el modelo se reinicia Django. La evaluación de requisitos sigue calculándose con datos actuales en cada consulta.

## Modelo y reproducción

- Repositorio: [Sentence Transformers, paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2), revisión `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, licencia Apache-2.0. Se usa exclusivamente `onnx/model_quint8_avx2.onnx` y los cinco archivos auxiliares enumerados en `backend/scripts/download_semantic_model.py`.
- Se ejecuta con ONNX Runtime `CPUExecutionProvider`, tokenizer local, truncamiento a 128 tokens, mean pooling con máscara y normalización L2. Requiere CPU AVX2; no requiere GPU, PyTorch ni conexión durante la recomendación.
- Instalación desde la raíz en Windows: ` .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt ` y después ` .\.venv\Scripts\python.exe backend\scripts\download_semantic_model.py `. El script comprueba AVX2, descarga solo los archivos permitidos de la revisión fijada y crea un manifiesto local con tamaños y SHA-256.
- Destino predeterminado: `D:\Proyectos\BecaNexo\.local-models\miniLM-multilingual`, ignorado por Git. Se puede configurar `SEMANTIC_MODEL_DIR` para otra ruta local; debe contener la misma estructura. La descarga verificada ocupó 127 536 988 bytes en los seis artefactos del modelo, más metadatos locales y paquetes del entorno virtual. SHA-256 del ONNX: `98a01d88b7de996cdea58c32ca71208c09968d143798814b2ea09d3439dc334f`; del tokenizer: `2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8`.
- `backend/requirements.in` declara las dependencias directas; `backend/requirements.txt` fija las versiones instaladas. La prueba `convocatorias.test_recomendaciones` ejecuta inferencia real si el modelo está presente y prueba el modo sin modelo con una sustitución controlada.

## Becas similares (v1.1, 27/11/2026)

El detalle de cada beca muestra «Becas similares»: hasta cuatro becas parecidas por su contenido. Usa el mismo embedding y el mismo texto de convocatoria que «Para ti» (`vector_convocatoria(texto_convocatoria(c))`), así que hay un solo criterio. No depende del perfil ni de la sesión, y no indica que la persona cumpla los requisitos.

- **Vectores guardados:** la tabla técnica `TEC_VECTOR_CONVOCATORIA` (migración `convocatorias.0014`) guarda un vector por convocatoria:
  - `vector`: float32 normalizado de 384 dimensiones, en bytes;
  - `version_modelo`;
  - `hash_texto`: SHA-256 del texto usado;
  - `actualizado_en`.

  Es un dato derivado que no figura en el ER: no es una entidad de negocio y se puede recalcular entero. Se borra con su convocatoria. Para revertirla: `manage.py migrate convocatorias 0013`.
- **Cálculo al publicar:** al publicar, o al volver a publicar tras editar, se recalcula solo si cambió el texto o el modelo. Se hace después de confirmar la publicación: si el modelo falla, se registra un aviso y la publicación sigue (`convocatorias/vectores.py`, `actualizar_sin_bloquear`).
- **Comando:** `manage.py calcular_vectores_convocatorias [--dry-run] [--forzar]` rellena o recalcula los vectores de las convocatorias públicas. Es idempotente y termina con un resumen: calculadas, al día, fallidas y segundos.
- **Endpoint:** `GET /api/becas/<id>/similares/` tiene la misma visibilidad que el detalle público (`publicas()`). Nunca devuelve la propia beca, borradores, pausadas ni becas de entidades no ecuatorianas.
  - Calcula la similitud coseno con numpy sobre los vectores guardados, sin cargar el modelo.
  - Umbral mínimo: 0,65. Entre las 55 convocatorias públicas reales, la mediana de los pares es 0,57; por debajo de 0,65 casi solo coinciden en lo genérico.
  - Las vigentes (abiertas, próximas, sin fecha o que cierran hoy) van antes que las cerradas, que se muestran con su estado.
  - Si falta el vector de la beca consultada, se calcula y se guarda una sola vez; si el modelo no está disponible, la lista queda vacía. Sin resultados, la interfaz no muestra la sección.

## Sugerencia en la comparación de requisitos (v1.1)

En el detalle de una beca, la comparación puede añadir a un requisito `TITULO_AREA` pendiente una «Posible coincidencia (sugerida por IA local)», con umbral 0,70 y el mismo modelo.

- Es solo información: no cambia el resultado del requisito, la elegibilidad ni el orden de «Para ti», y no acredita nada.
- El texto del requisito usa la caché de textos públicos. El de la formación declarada se calcula en cada consulta y no se guarda.
- Detalle en [api-comparacion.md](api-comparacion.md).

## Interpretación y límites

La interfaz muestra por separado el resultado de requisitos y si la afinidad temática fue calculada. Si faltan datos temáticos del perfil, indica qué completar; si falta o falla el modelo, conserva el orden basado en reglas y muestra afinidad pendiente. No se envían datos a servicios externos ni se predice adjudicación. El modelo multilingüe es genérico: puede ordenar mal términos especializados, depende del texto disponible y trunca entradas largas. Sus similitudes no son probabilidades. Las ponderaciones futuras 70/10/10/10 de la documentación de decisiones no se aplican en este bloque porque faltan validación y un contrato de afinidad completa.
