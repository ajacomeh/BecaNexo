export const bool = [{ value: 'true', label: 'Sí' }, { value: 'false', label: 'No' }]
export const choices = (rows, key = 'id') => rows.map((r) => ({ value: r[key], label: r.nombre }))
export const enumOptions = (values) => values.map((v) => ({ value: v, label: v.replaceAll('_', ' ') }))
const text = (name, label, extra = {}) => ({ name, label, ...extra })
const select = (name, label, options, extra = {}) => text(name, label, { options, ...extra })
export const institutionFields = (catalogs) => [text('nombre', 'Nombre oficial', { required: true }),
  select('sector', 'Sector', enumOptions(['publico', 'privado']), { required: true }),
  select('pais', 'País de la entidad oferente', choices(catalogs.paises.filter((p) => p.codigo === 'EC')), { kind: 'id', required: true }), text('url_oficial', 'Web institucional', { type: 'url' })]
export const generalFields = (c, institutions) => [text('titulo', 'Título', { required: true, maxLength: 250 }),
  select('institucion', 'Entidad oferente ecuatoriana', choices(institutions), { kind: 'id', required: true }),
  select('tipo_beca', 'Tipo de beca', choices(c.tipos_beca), { kind: 'id' }), text('url_oficial', 'Enlace oficial', { type: 'url', blank: true }),
  text('url_bases', 'Enlace de las bases', { type: 'url' }), text('descripcion', 'Descripción', { type: 'textarea', wide: true, blank: true }),
  text('fecha_publicacion', 'Fecha de publicación en la fuente', { type: 'date' }),
  text('apertura', 'Apertura (America/Guayaquil)', { type: 'datetime-local' }), text('cierre', 'Cierre (America/Guayaquil)', { type: 'datetime-local' }),
  text('cierre_original', 'Texto original del cierre'), select('cobertura_tipo', 'Cobertura según las bases', enumOptions(['total', 'parcial', 'mixta', 'no_especificada'])),
  text('gastos_no_cubiertos', 'Gastos no cubiertos', { type: 'textarea' }), text('obligaciones_beneficiario', 'Obligaciones del beneficiario', { type: 'textarea' }),
  select('areas', 'Áreas académicas', choices(c.areas), { multiple: true, kind: 'ids' })]
export const optionFields = (c) => [select('nivel', 'Nivel', choices(c.niveles, 'valor'), { required: true }),
  select('modalidad', 'Modalidad', choices(c.modalidades, 'valor'), { required: true }),
  select('activa', 'Opción activa', bool, { required: true, kind: 'boolean' }), text('programa', 'Programa'), text('institucion_destino', 'Institución de destino'),
  text('inicio_estudios', 'Inicio de estudios', { type: 'date' }), text('duracion_meses', 'Duración en meses', { type: 'number', kind: 'integer' }),
  text('cupos', 'Cupos', { type: 'number', kind: 'integer' }), select('paises', 'Países de estudio', choices(c.paises), { multiple: true, kind: 'ids' })]
const scope = (options) => select('opcion_estudio', 'Ámbito (sin declarar = común)', options.map((o) => ({ value: o.id, label: `${o.nivel} / ${o.modalidad} · #${o.id}` })), { kind: 'id' })
export const benefitFields = (options) => [scope(options), text('concepto', 'Concepto financiado', { required: true }),
  text('porcentaje', 'Porcentaje de este concepto', { type: 'number', kind: 'number' }), text('monto', 'Monto', { type: 'number', kind: 'number' }),
  text('moneda', 'Moneda (código de tres letras)', { maxLength: 3 }), select('periodicidad', 'Periodicidad', enumOptions(['unico', 'mensual', 'anual', 'otra'])), text('detalle', 'Detalle de cobertura', { type: 'textarea' })]
export const requirementFields = (type, c, options) => {
  const fields = [scope(options), text('texto_original', 'Texto original del requisito', { type: 'textarea', required: true }),
    select('obligatorio', 'Condición obligatoria', bool, { kind: 'boolean', required: true }), select('validado', 'Transcripción revisada por administrador', bool, { kind: 'boolean', required: true }),
    select('activo', 'Requisito activo', bool, { kind: 'boolean', required: true }), text('fecha_referencia', 'Fecha de referencia según las bases', { type: 'date' }),
    text('referencia_bases', 'Referencia en las bases'), text('documento_exigido', 'Documento exigido (lo verifica el oferente)'), text('detalle_acreditacion', 'Condiciones de acreditación externa', { type: 'textarea' })]
  for (const [name, spec] of Object.entries(type.esquema_valor.campos)) {
    const f = { name: `regla_${name}`, label: spec.label, required: spec.required, kind: spec.kind }
    if (['paises', 'pais'].includes(spec.kind)) f.options = choices(c.paises, 'codigo')
    else if (['areas', 'area'].includes(spec.kind)) { f.options = choices(c.areas); f.kind = spec.kind === 'areas' ? 'ids' : 'id' }
    else if (spec.kind === 'idioma') f.options = choices(c.idiomas, 'codigo')
    else if (spec.kind === 'boolean') f.options = bool
    else if (spec.options) f.options = enumOptions(spec.options)
    if (['paises', 'areas', 'lista'].includes(spec.kind)) f.multiple = true
    if (['number', 'integer'].includes(spec.kind)) f.type = 'number'
    if (spec.kind === 'textos' || (spec.kind === 'text' && !spec.options)) f.type = 'textarea'
    fields.push(f)
  }
  return fields
}
