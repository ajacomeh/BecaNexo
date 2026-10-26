# Presentación del catálogo público

La ruta `/becas` comparte presentación para visitantes y postulantes. La gestión administrativa conserva sus formularios y tarjetas. No cambia el contrato de la API ni se realizan peticiones de detalle por tarjeta.

## Filtros, orden y página

- Búsqueda, nivel, modalidad y destino siempre visibles. Tipo de beca y estado se encuentran en el elemento nativo accesible «Más filtros». Cerrarlo conserva sus selecciones; el contador indica filtros secundarios **aplicados en la URL**, no borradores del formulario.
- Los valores vacíos significan no filtrar («Todos…»), exclusivamente en este catálogo. Los estados públicos siguen siendo `abierta`, `cerrada`, `proxima` y `sin_fecha`.
- «Aplicar filtros» actualiza la URL y elimina `page`. «Limpiar filtros» elimina búsqueda, filtros, orden y página; vuelve al orden predeterminado del servidor.
- «Ordenar por» se aplica inmediatamente sobre los filtros de la URL, con vuelta a página uno. Las selecciones de filtros aún no aplicadas deben confirmarse con «Aplicar filtros» antes de cambiar el orden. `recientes` es el orden real predeterminado: `-actualizado_en, -id`; las alternativas existentes son `titulo` y `cierre` (fechas desconocidas al final). No se cambian estos criterios.
- La paginación solo se muestra cuando `count > page_size`. No se deducen páginas del número de tarjetas. Se mantienen los parámetros aplicados al avanzar o retroceder.

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
