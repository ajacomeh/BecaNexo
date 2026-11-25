# Presentación del catálogo público

La ruta `/becas` comparte presentación para visitantes y postulantes. BecaNexo está dirigido a ciudadanos ecuatorianos: por defecto el catálogo lista solo becas con entidad oferente ecuatoriana asignada. No se realizan peticiones de detalle por tarjeta.

## Filtro compacto, orden y página (25/11/2026)

El filtro es el componente `frontend/src/components/CompactFilters.jsx`, compartido con Convocatorias del administrador. En el catálogo público:

- **Búsqueda** a todo el ancho, con lupa y etiqueta accesible. Se aplica al dejar de escribir (400 ms) o al pulsar Enter.
- **Una fila de controles** que se aplican al cambiar: Nivel, Modalidad y Destino de estudio, el destino rápido «Todos / Ecuador / Extranjero» y el interruptor «Incluir entidades no ecuatorianas» (desactivado por defecto, con ayuda accesible).
- **Destino rápido:** elegir un país concreto limpia el destino rápido, y al revés.
- **Opciones de los selectores:** solo muestran los valores presentes según las facetas del servidor, con su número de resultados entre paréntesis. El valor elegido se conserva aunque tenga 0.
- **Fichas de filtros activos:** cada filtro aplicado aparece como una ficha con un botón «Quitar filtro …». «Limpiar todo» solo aparece con filtros activos, quita los filtros y conserva la pestaña de vigencia y el orden. Al quitar una ficha, el foco pasa al buscador.
- **Tipo de beca** no tiene control en el catálogo público. El parámetro `tipo_beca` sigue admitido por la API y, si llega por URL, se muestra como ficha para poder quitarlo.
- **Cambios y URL:** cada cambio vuelve a la página 1 y queda en la URL, incluido `incluir_no_ecuatorianas`. Se conserva al cambiar de pestaña, paginar y recargar. Solo la última consulta actualiza los resultados.
- **Pestañas, contador y orden:** las pestañas de vigencia (Vigentes, Próximas, Cerradas, Todas las publicadas), el contador de resultados (`role="status"`) y «Ordenar por» van en la misma fila. El orden se aplica al seleccionar: `recientes` (`-actualizado_en, -id`, predeterminado), `titulo` o `cierre` (fechas desconocidas al final).
- **Móvil:** por debajo de 640 px, los controles se pliegan tras el botón «Filtros (n)», con `aria-expanded` y el número de filtros activos. El buscador queda siempre visible.
- **Paginación:** solo aparece cuando `count > page_size` y conserva los parámetros aplicados.

### Parámetros de `GET /api/becas/`

Definidos en `backend/convocatorias/api.py` (`filtrar` y `Consulta`). Un parámetro desconocido o repetido devuelve 400.

| Parámetro | Valores |
|---|---|
| `q` | Texto de hasta 200 caracteres: título, entidad oferente, área, descripción o programa de una opción |
| `nivel`, `modalidad` | Valores del catálogo de opciones de estudio |
| `destino` | Código de país |
| `destino_ambito` | `ecuador` (la opción tiene Ecuador como destino) o `exterior` (algún destino distinto de Ecuador). Devuelve 400 si el valor es inválido o se combina con `destino` |
| `tipo_beca` | ID del tipo |
| `estado` | `vigentes` (predeterminado sin parámetro), `abierta`, `cierre_hoy`, `proxima`, `cerrada`, `sin_fecha` o `todas` |
| `orden` | `recientes`, `titulo` o `cierre` |
| `page`, `page_size` | Página desde 1; 12 por defecto, máximo 50 |
| `incluir_no_ecuatorianas` | `false` por defecto (solo entidades ecuatorianas). Admite `true`/`1` o `false`/`0`; otro valor devuelve 400 |

`nivel`, `modalidad`, `destino` y `destino_ambito` se evalúan en una única subconsulta: todos deben cumplirse en la misma opción de estudio activa.

La respuesta añade `facetas`, con estos campos:

- `nivel`, `modalidad` y `destino`: listas de `{valor, total}`.
- `destino_ambito`: `{ecuador, exterior}`.

Siguen la pestaña, el interruptor, `tipo_beca` y la búsqueda. El conteo de cada dimensión se calcula sin su propio filtro (búsqueda facetada), y la faceta de destino ignora tanto `destino` como `destino_ambito`. Las pruebas están en `backend/convocatorias/test_catalogo_facetas.py` y `test_catalogo_ecuatorianas.py`.

## Convocatorias del administrador (25/11/2026)

`/gestion/convocatorias` usa el mismo `CompactFilters` con su propia configuración:

- Buscador y una fila con Nivel, Modalidad, Destino de estudio, Tipo de beca y Estado (borrador, pausada, abierta, cerrada, próxima y sin fecha).
- La misma aplicación al instante, fichas, «Limpiar todo» y «Filtros (n)» en móvil.
- No tiene interruptor de entidades, destino rápido ni conteos: el listado `GET /api/gestion/convocatorias/` no admite `incluir_no_ecuatorianas` ni `destino_ambito` (400) y no devuelve facetas. Acepta además `revision`.

Las tarjetas de esa pantalla usan la presentación del catálogo (piezas comunes de `frontend/src/components/CardParts.jsx`):

- Bloques con icono, etiqueta y valor: Cierre, Opciones de estudio, Nivel o Niveles, Modalidades y Tipo. Tipo solo aparece si tiene un valor.
- La franja «Financiamiento».
- El pie con «Editar y revisar».

Conservan el aviso de pasos pendientes para publicar, el origen del rastreo, la ficha retirada, el oferente y las etiquetas de estado.

## Resúmenes fieles al contrato actual

- El listado público ya entrega `opciones` activas y beneficios comunes o vinculados a opciones activas. El frontend utiliza esos datos; no filtra ni amplía las reglas de publicación.
- `opciones[].paises` contiene identificadores: se resuelven contra `becas/catalogos.paises`. Se cuentan países distintos, nunca el país del oferente. Las listas de niveles y modalidades se deduplican y se aclara que las combinaciones concretas están en el detalle.
- Se omiten tipo, beneficios y opciones vacíos. Se conservan títulos DEMOSTRACIÓN. No se modifica la información del detalle.
- Los porcentajes conservan decimales significativos y nombran el concepto financiado. No se suman ni se extrapolan a gastos totales. Un beneficio sin porcentaje muestra apoyo y consulta de condiciones, sin convertir montos. Un beneficio específico se marca como tal; si hay varios específicos se remite prudentemente a condiciones por opción, sin destacar un porcentaje general.
- Fechas breves en `es-EC`, zona `America/Guayaquil`; el detalle conserva la hora. Sin fecha se muestra el texto `cierre_original` si está informado, atribuido a la fuente; en su ausencia, una sola leyenda «Fecha de cierre no informada». No hay un campo estructurado de permanencia en el contrato actual y no se deduce ni se añade una regla de permanencia. El estado `sin_fecha` no se repite como insignia.
- «Ver detalle» es la acción principal. Favoritos conserva el componente existente, errores, carga y retorno seguro desde login, sin guardado automático. No se ofrecen controles de favoritos al administrador.

## Verificación reproducible

Desde `frontend`, con Node 24 en PATH:

```powershell
npm.cmd test -- --maxWorkers=1
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e -- --config playwright.layout.config.js
```

Las pruebas visuales usan respuestas interceptadas y datos ficticios, sin escribir en PostgreSQL. Cubren roles, anchos de escritorio/móvil, filtros, paginación, desplazamiento y acceso al cierre de sesión. El reflujo a 720×450 no equivale a haber accionado el zoom nativo de Edge: esa comprobación manual sigue pendiente.
