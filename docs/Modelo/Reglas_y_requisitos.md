# BecaNexo v0.5 · Contrato lógico de requisitos

Diseño propuesto; no es una base de datos implementada. El administrador revisa la información de la oferta, no los documentos del postulante. Todos los ejemplos del prototipo son ficticios.

## Qué cambia y por qué

- Se conserva `MAE_USUARIO.nombre`, email, hash de contraseña, rol, activo y fecha. Se elimina nombre_usuario. `nombre` identifica a la persona, no es credencial de acceso.
- `REL_PERFIL_IDIOMA` contiene id, perfil_id, idioma_id y nivel. Se eliminan certificacion y fecha_certificacion. No se crean tablas de archivos o certificados del usuario.
- `MAE_FORMACION` distingue estado de estudios, título obtenido, nombre del título, área y fecha de finalización. No se equipara cursar una carrera con haberla concluido.
- `MAE_PERFIL` agrega residencia local y disponibilidad. `residencia_id` sigue siendo FK a CAT_PAIS: representa país de residencia; provincia y ciudad son texto opcional en esta versión.
- `MAE_EXPERIENCIA` sustituye el total ambiguo experiencia_meses por registros de área y fechas. Los meses se calculan para la condición correspondiente, sin duplicar periodos solapados. No registrar experiencias significa desconocido, no cero.
- `CAT_TIPO_BECA` permite clasificar la oferta. En esta versión cada convocatoria tiene una clasificación principal opcional.
- `MAE_BENEFICIO` separa cada concepto financiado, porcentaje, monto, moneda y periodicidad. Sustituye cobertura_pct/cobertura_detalle a nivel general de convocatoria. Permite condiciones comunes y específicas por opción.
- `CAT_TIPO_REQUISITO` define el contrato de datos de cada condición y los operadores admitidos. `MAE_REQUISITO` conserva el texto de origen, el valor estructurado, el ámbito, la referencia a las bases y la forma de comprobación.
- `TRA_EVALUACION_REQUISITO` conserva los datos comparados y distingue comparación declarada de condición externa. No contiene archivos probatorios del usuario.

## Estructura de cada requisito

Cada fila de MAE_REQUISITO representa una condición. `opcion_estudio_id` vacío significa que aplica a todas las opciones; si está presente, debe pertenecer a la convocatoria indicada. No almacenar varias condiciones independientes en una sola regla ambigua. El administrador completa campos de formulario; el backend construirá el objeto estructurado, no se pedirá escribir JSON en la interfaz.

`valor_estructurado` debe validarse contra el contrato del tipo. La presencia de JSON no implica admitir contenido arbitrario. `obligatorio` expresa la exigencia de las bases; `validado` significa que el administrador revisó la transcripción del requisito, nunca que un usuario lo haya acreditado.

| Código de tipo | Campos del valor estructurado | Dato del perfil | Comparación |
|---|---|---|---|
| NACIONALIDAD | codigos_pais admitidos | nacionalidad_id | pertenencia; alcance EC |
| FORMACION | nivel_minimo, estado_exigido, titulo_obtenido | nivel, estado_estudios, titulo_obtenido | nivel con orden explícito + estados |
| TITULO_AREA | titulos_admitidos, areas_admitidas | nombre_titulo, area_id | catálogo/equivalencia revisada; no concluir equivalencia legal por similitud |
| EDAD | minimo opcional, maximo opcional | fecha_nacimiento | años cumplidos a fecha_referencia definida en bases |
| PROMEDIO | minimo, escala_min, escala_max, equivalencia_documentada opcional | promedio, escala_min, escala_max | solo escalas comparables o conversión explícita documentada |
| IDIOMA | codigo_idioma, nivel_minimo | idioma_id, nivel | jerarquía A1,A2,B1,B2,C1,C2; otros marcos requieren regla documentada |
| EXPERIENCIA | meses_minimos, area requerida opcional | experiencias por área y fechas | meses correspondientes; ausencia de datos = pendiente |
| DEDICACION | valores_admitidos | dedicacion_disponible | pertenencia; sin dato = pendiente |
| TRASLADO | requerido, destino opcional | disponible_traslado, disponible_extranjero | declaración; cualquier restricción específica no capturada queda pendiente |
| RESIDENCIA | países/provincias/ciudades admitidos | residencia_id, provincia_residencia, ciudad_residencia | ubicación normalizada; ambigüedad = pendiente |
| ACREDITACION | detalle de certificados admitidos, vigencia si publicada | no se solicita al usuario | entidad_oferente; informar, sin acreditar |
| DOCUMENTO | título, carta, admisión u otro documento exigido | no se carga al sistema | entidad_oferente; informar, sin acreditar |
| OTRO | descripción publicada | solo si existe dato y regla autorizada | por defecto pendiente/externo, no inferir cumplimiento |

Ejemplos: idioma {codigo_idioma: "en", nivel_minimo: "B2"}; edad {maximo: 35}, fecha_referencia=30/11/2026; promedio {minimo: 8, escala_min: 0, escala_max: 10}. Certificado B2 es una fila separada de la condición idioma B2.

## Estados y alcance de las conclusiones

Resultado por condición: `cumple_declarado`, `no_cumple_declarado`, `pendiente_datos` o `verificacion_externa`. Una condición externa no se muestra como cumplida ni penaliza la afinidad temática como si se hubiera comprobado un incumplimiento. La recomendación puede ordenar coincidencias declaradas y mostrar por separado todas las acreditaciones externas.

El atributo heredado `elegibilidad` representa una conclusión ORIENTATIVA: `compatible_declarado`, `incumplido_declarado` o `pendiente`. No representa elegibilidad oficial. Cualquier incumplimiento obligatorio declarado impide mostrar cumplimiento global. Información faltante mantiene pendiente la comparación correspondiente. Todas las condiciones externas conservan su estado explícito en las evaluaciones.

La frase «no se exige experiencia» solo se utilizará si las bases lo confirman. Si simplemente no la mencionan, se mostrará «No especificado» y no se inventará un requisito. En el ejemplo visual no se ha configurado una regla automática de experiencia.

## Integridad y validaciones previstas

- Todas las FK deben apuntar a registros existentes. Las relaciones simples del diagrama se complementarán con controles de coherencia de ámbito.
- Nacionalidad del postulante e institución oferente: EC. Una página ecuatoriana que republica una oferta extranjera no convierte al oferente en ecuatoriano.
- Al publicar: institución validada, al menos una opción activa, URL oficial y requisitos revisados. Sin tipo, monto o fecha publicados se preserva el dato ausente; la UI indica «No especificado».
- Requisito, beneficio y recomendación no pueden apuntar a una opción de otra convocatoria. Evaluaciones deben pertenecer a requisitos comunes o de la misma opción recomendada.
- Porcentaje entre 0 y 100, por concepto. Monto no negativo y moneda obligatoria cuando exista monto. Cupos y duración positivos cuando estén informados.
- No sumar ni superponer un beneficio común y uno específico para el mismo concepto sin aclarar si sustituye o complementa; el administrador debe resolverlo antes de publicar.
- `tipo_beca_id` es opcional si la fuente no lo especifica. El nombre de la beca no determina por sí solo el tipo.
- `titulo_obtenido=true` requiere estudios concluidos; una formación en curso no debe tener fecha final real. La fecha de nacimiento no puede ser futura. Una experiencia actual no lleva fecha de fin; una finalizada exige un intervalo válido.
- Las combinaciones de preferencia nivel/modalidad son múltiples filas. `nivel` y `modalidad` permanecen como dominios controlados, no nuevas tablas en esta revisión.
- Mantener unicidad de pares en tablas REL: perfil+idioma, perfil+área, perfil+país, opción+país, convocatoria+área y usuario+convocatoria en favoritos. También perfil+nivel+modalidad en preferencias.
- La identidad de opción sigue siendo convocatoria+nivel+modalidad. Si se necesitan programas distintos dentro de la misma combinación, deberá ampliarse la identidad antes de programar ese caso. Si cambian requisitos por destino dentro de una misma opción, requerirá un ámbito adicional; no se fingirá compatibilidad común.
- Versionar los cambios de perfil, convocatoria y configuración; conservar instantáneas suficientes de reglas, datos comparados y textos utilizados. Un número de versión solo no reproduce resultados pasados.
- Notificación al usuario dueño del perfil de la recomendación. Auditoría con exactamente un objeto entre convocatoria, fuente o configuración.

## Convención

CAT: catálogo. MAE: entidad principal o detalle estable del negocio. REL: asociación. CFG: configuración. TRA: ejecución o resultado operacional. AUD: auditoría. TEC: soporte técnico.

Los nombres en mayúsculas son los del modelo presentado. La convención física de nombres y migraciones se definirá al construir PostgreSQL/Django; no se entrega SQL.
