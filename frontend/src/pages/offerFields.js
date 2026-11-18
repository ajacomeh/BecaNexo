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
  select('alcance_academico', 'Alcance académico verificado', [
    { value: 'pendiente', label: 'Pendiente de confirmar' },
    { value: 'programas', label: 'Programas específicos' },
    { value: 'transversal', label: 'Transversal institucional' },
  ], { required: true, hint: 'Este alcance describe la fuente; no confirma por sí solo la elegibilidad de un postulante.' }),
  text('alcance_detalle', 'Programas o población académica respaldada', { type: 'textarea', wide: true, hint: 'Describe únicamente lo indicado en la fuente oficial.' }),
  text('alcance_exclusiones', 'Carreras excluidas', { type: 'textarea', wide: true }),
  text('alcance_sede', 'Sede documentada'),
  text('alcance_periodo', 'Período académico documentado', { hint: 'Conserva el período literal; no inventes una fecha de inicio.' }),
  text('fecha_publicacion', 'Fecha de publicación en la fuente', { type: 'date' }),
  text('apertura', 'Apertura (America/Guayaquil)', { type: 'datetime-local' }), text('cierre', 'Cierre con hora confirmada (America/Guayaquil)', { type: 'datetime-local' }),
  text('cierre_dia', 'Día de cierre sin hora informada', { type: 'date', hint: 'Usa este campo solo cuando la fuente no indique hora. Deja vacío el cierre con hora.' }),
  text('cierre_original', 'Texto original del cierre', { hint: 'Conserva el literal de la fuente para un cierre expresado solo como día.' }), select('cobertura_tipo', 'Cobertura según las bases', enumOptions(['total', 'parcial', 'mixta', 'no_especificada'])),
  text('gastos_no_cubiertos', 'Gastos no cubiertos', { type: 'textarea' }), text('obligaciones_beneficiario', 'Obligaciones del beneficiario', { type: 'textarea' }),
  select('areas', 'Áreas académicas', choices(c.areas), { multiple: true, kind: 'ids' })]
export const optionFields = (c) => [select('nivel', 'Nivel', choices(c.niveles_opcion || c.niveles, 'valor'), { required: true }),
  select('modalidad', 'Modalidad', choices(c.modalidades, 'valor'), { required: true }),
  select('activa', 'Opción activa', bool, { required: true, kind: 'boolean' }), text('programa', 'Programa'), text('institucion_destino', 'Institución de destino'),
  text('inicio_estudios', 'Inicio de estudios', { type: 'date' }), text('duracion_meses', 'Duración en meses', { type: 'number', kind: 'integer' }),
  text('cupos', 'Cupos', { type: 'number', kind: 'integer' }), select('paises', 'Países de estudio', choices(c.paises), { multiple: true, kind: 'ids' })]
const optionDescription = (option, countries) => [option.programa || 'Programa no especificado', `${option.nivel} / ${option.modalidad}`,
  option.institucion_destino, (option.paises || []).map(id => countries.find(country => country.id === id)?.nombre || String(id)).join(', ')].filter(Boolean).join(' · ')
export const optionLabel = (option, countries = [], options = []) => {
  const description = optionDescription(option, countries)
  return options.filter(other => optionDescription(other, countries) === description).length > 1 ? `${description} · #${option.id}` : description
}
const scope = (options, countries) => select('opcion_estudio', 'Ámbito (sin declarar = común)', options.map((o) => ({ value: o.id, label: optionLabel(o, countries, options) })), { kind: 'id' })
export const benefitFields = (options, countries = []) => [scope(options, countries), text('concepto', 'Concepto financiado', { required: true }),
  text('porcentaje', 'Porcentaje de este concepto', { type: 'number', kind: 'number' }), text('monto', 'Importe fijo (no es tope)', { type: 'number', kind: 'number' }),
  text('moneda', 'Moneda del importe fijo', { maxLength: 3 }), text('tope_original', 'Tope literal según las bases', { hint: 'Conserva el símbolo y texto originales; $ no confirma USD.' }),
  text('tope_monto', 'Valor máximo del tope, si está claro', { type: 'number', kind: 'number' }), text('tope_moneda', 'Moneda confirmada del tope (opcional)', { maxLength: 3, hint: 'Deja vacío si la fuente no confirma el código monetario.' }),
  select('periodicidad', 'Periodicidad', enumOptions(['unico', 'mensual', 'anual', 'otra'])), text('detalle', 'Detalle de cobertura', { type: 'textarea' })]
export const requirementFields = (type, c, options) => {
  const documental = ['DOCUMENTO', 'ACREDITACION'].includes(type.codigo)
  const fields = [scope(options, c.paises), text('texto_original', 'Texto original del requisito', { type: 'textarea', required: true }),
    select('destino', 'Destino específico (requiere opción; vacío = todos)', choices(c.paises), { kind: 'id' }),
    select('obligatorio', 'Condición obligatoria', bool, { kind: 'boolean', required: true }), select('validado', 'Transcripción revisada por administrador', bool, { kind: 'boolean', required: true }),
    select('activo', 'Requisito activo', bool, { kind: 'boolean', required: true }), text('fecha_referencia', 'Fecha de referencia según las bases', { type: 'date' }),
    text('referencia_bases', 'Referencia en las bases'), text('documento_exigido', 'Documento exigido (lo verifica el oferente)'), text('detalle_acreditacion', 'Condiciones de acreditación externa', { type: 'textarea' })]
  if (['FORMACION', 'TITULO_AREA', 'PROMEDIO'].includes(type.codigo)) fields.push(
    select('relacion_formacion', 'Relación entre condiciones académicas', [{ value: 'pendiente', label: 'No definida (pendiente)' }, { value: 'independiente', label: 'Condición independiente' }, { value: 'misma_formacion', label: 'Debe cumplirse en una misma formación' }], { required: true }),
    text('grupo_formacion', 'Clave del grupo de misma formación', { maxLength: 64 }))
  if (['TITULO_AREA', 'RESIDENCIA'].includes(type.codigo)) fields.push({ name: 'equivalencias', label: 'Equivalencias revisadas en las bases', kind: 'equivalencias', codigo: type.codigo, paises: c.paises, wide: true })
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
  if (documental) {
    Object.assign(fields.find(f => f.name === 'opcion_estudio'), { label: 'Ámbito', placeholder: 'Toda la convocatoria' })
    fields.find(f => f.name === 'texto_original').label = 'Descripción e instrucciones según las bases'
    Object.assign(fields.find(f => f.name === 'detalle_acreditacion'), {
      label: type.codigo === 'DOCUMENTO' ? 'Detalle complementario de acreditación' : 'Condiciones o alternativas según las bases',
      supplementary: type.codigo === 'DOCUMENTO',
    })
    Object.assign(fields.find(f => f.name === 'documento_exigido'), { label: 'Documento complementario', supplementary: true })
    fields.find(f => f.name === 'obligatorio').label = 'Documento obligatorio según las bases'
    fields.find(f => f.name === 'validado').hint = 'Confirma que cotejaste la transcripción con las bases. No acredita documentos del postulante.'
    fields.find(f => f.name === 'fecha_referencia').hint = 'Fecha publicada para evaluar la condición; no es la fecha de registro. Déjala vacía si las bases no la indican.'
    const link = fields.find(f => f.name === 'regla_url_documento')
    if (link) link.hint = 'Enlace al documento o formulario exigido. Las bases oficiales se registran en los datos generales de la convocatoria.'
  }
  fields.filter(f => f.kind === 'url').forEach(f => { f.type = 'url' })
  return fields
}
