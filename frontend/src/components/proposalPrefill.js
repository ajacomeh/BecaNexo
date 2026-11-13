// Sugerencias de trabajo a partir del HTML de la versión exacta. No confirma catálogos.
const literal = (value, limit) => typeof value === 'string' && value.trim().length <= limit ? value.trim() : ''
const original = (value, limit) => literal(value?.texto_original || value?.original, limit)

export function proposalPrefill(version, documents, current = {}) {
  const extracted = version?.datos_extraidos || {}
  const data = { ...current }
  const references = []
  const html = documents.find((item) => item.rol === 'ficha_html' && item.evidencia_id)
  if (!html) return { data, references }
  function add(field, value, section, kind = 'literal') {
    if (!value) return
    if (data[field] !== undefined && data[field] !== null && data[field] !== '') return
    data[field] = value
    if (html) references.push({ campo: field, evidencia_id: html.evidencia_id, localizador: section,
      original: kind === 'interpretado' ? original(extracted.cierre, 15000) : value,
      motivo: kind === 'interpretado' ? 'Fecha de día normalizada por el extractor; revisar antes de confirmar.' : 'Transcripción literal de la ficha HTML; verificar contra las bases.' })
  }
  add('titulo', original(extracted.titulo, 250), 'Título de la ficha')
  add('descripcion', original(extracted.descripcion, 15000), 'Descripción de la ficha')
  add('cierre_original', original(extracted.cierre, 500), 'POSTULA HASTA')
  if (original(extracted.cierre, 500) && /^\d{4}-\d{2}-\d{2}$/.test(extracted.cierre?.fecha || '')) {
    add('cierre_dia', extracted.cierre.fecha, 'POSTULA HASTA', 'interpretado')
  }
  const studies = extracted.estudios || {}
  const modality = original(studies.modalidad, 60)
  const destination = original(studies.destino, 500)
  if (modality || destination) {
    if (data.opciones === undefined) data.opciones = [{ id: 'ficha-estudios', texto: '', modalidad: modality, destinos: destination, ambito: 'pendiente' }]
  }
  for (const [field, item, section, id] of [
    ['beneficios', extracted.beneficio, 'Cobertura de la ficha', 'ficha-beneficio'],
    ['requisitos', extracted.requisitos, 'Requisitos generales de la ficha', 'ficha-requisitos'],
  ]) {
    const value = original(item, 5000)
    if (!value) continue
    if (data[field] === undefined) {
      data[field] = [{ id, texto: value, ambito: 'pendiente' }]
      if (html) references.push({ campo: `${field}.${id}`, evidencia_id: html.evidencia_id, localizador: section,
        original: value, motivo: 'Transcripción literal de la ficha HTML; alcance y bases pendientes de revisión.' })
    }
  }
  return { data, references }
}
