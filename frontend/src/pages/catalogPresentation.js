export const readable = (value) => ({ maestria: 'Maestría', doctorado: 'Doctorado', grado: 'Grado', tecnologico: 'Tecnológico', tecnico: 'Técnico', especializacion: 'Especialización', presencial: 'Presencial', virtual: 'Virtual', hibrida: 'Híbrida' }[value] || (value ? value.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()) : ''))
export const unique = values => [...new Set(values.filter(Boolean))]

export function benefitSummary(benefits) {
  const specific = benefits.filter(b => b.opcion_estudio != null)
  const common = benefits.filter(b => b.opcion_estudio == null)
  const describe = b => b.porcentaje != null ? `${String(b.porcentaje).replace(/(\.\d*?[1-9])0+$|\.0+$/, '$1')} % de ${b.concepto.toLocaleLowerCase('es')}` : `Apoyo para ${b.concepto.toLocaleLowerCase('es')} · Consulta las condiciones`
  return [...common.map(describe), ...(specific.length === 1 ? [`${describe(specific[0])} · Solo para una opción; consulta el detalle`] : specific.length > 1 ? ['Beneficios específicos por opción · Consulta las condiciones de cada opción en el detalle'] : [])]
}

