export const readable = (value) => ({ maestria: 'Maestría', doctorado: 'Doctorado', grado: 'Grado', tecnologico: 'Tecnológico', tecnico: 'Técnico', tecnico_superior: 'Técnico superior', tecnologico_superior: 'Tecnológico superior', maestria_tecnologica: 'Maestría tecnológica', especializacion: 'Especialización', no_aplica: 'No aplica (educación continua)', presencial: 'Presencial', virtual: 'Virtual', hibrida: 'Híbrida' }[value] || (value ? value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()) : ''))
export const unique = values => [...new Set(values.filter(Boolean))]

export function benefitSummary(benefits) {
  const specific = benefits.filter(b => b.opcion_estudio != null)
  const common = benefits.filter(b => b.opcion_estudio == null)
  const describe = b => {
    const concept = b.concepto.toLocaleLowerCase('es')
    const percentage = b.porcentaje != null ? `${String(b.porcentaje).replace(/(\.\d*?[1-9])0+$|\.0+$/, '$1')} % de ${concept}` : null
    const amount = b.monto != null && b.moneda ? `${b.monto} ${b.moneda} para ${concept}` : null
    const range = b.detalle?.match(/\bdel\s+(\d{1,3})\s*%\s+al\s+(\d{1,3})\s*%/iu)
    const conditionalRange = range && Number(range[1]) <= Number(range[2]) && Number(range[2]) <= 100
      ? `Del ${range[1]} % al ${range[2]} % de ${concept} · Rango condicionado; consulta los cupos y requisitos` : null
    const core = [percentage, amount].filter(Boolean).join(' · ') || conditionalRange
      || (b.detalle ? `${b.concepto} · Cobertura según condiciones publicadas` : `Apoyo para ${concept} · Porcentaje no informado`)
    return b.tope_original ? `${core} · Tope según bases: ${b.tope_original}${b.tope_moneda ? '' : ' (moneda no confirmada)'}` : core
  }
  return [...common.map(describe), ...(specific.length === 1 ? [`${describe(specific[0])} · Solo para una opción; consulta el detalle`] : specific.length > 1 ? ['Beneficios específicos por opción · Consulta las condiciones de cada opción en el detalle'] : [])]
}

