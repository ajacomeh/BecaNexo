// Estado de los filtros del catálogo público, compartido por el componente de filtros y la página del catálogo.
export const PUBLIC_FILTER_KEYS = ['q', 'nivel', 'modalidad', 'destino', 'destino_ambito', 'tipo_beca', 'incluir_no_ecuatorianas']
export const AMBITOS = [['', 'Todos'], ['ecuador', 'Ecuador'], ['exterior', 'Extranjero']]

export function activeFilters(params, catalogs) {
  const name = (rows, value, key = 'valor') => rows?.find(row => String(row[key]) === value)?.nombre || value
  const chips = []
  const q = params.get('q')
  if (q) chips.push({ key: 'q', label: `Búsqueda: «${q}»` })
  if (params.get('nivel')) chips.push({ key: 'nivel', label: `Nivel: ${name(catalogs.niveles_opcion || catalogs.niveles, params.get('nivel'))}` })
  if (params.get('modalidad')) chips.push({ key: 'modalidad', label: `Modalidad: ${name(catalogs.modalidades, params.get('modalidad'))}` })
  if (params.get('destino')) chips.push({ key: 'destino', label: `Destino: ${name(catalogs.paises, params.get('destino'), 'codigo')}` })
  const ambito = AMBITOS.find(([value]) => value && value === params.get('destino_ambito'))
  if (ambito) chips.push({ key: 'destino_ambito', label: `Destino: ${ambito[1]}` })
  if (params.get('tipo_beca')) chips.push({ key: 'tipo_beca', label: `Tipo de beca: ${name(catalogs.tipos_beca, params.get('tipo_beca'), 'id')}` })
  if (params.get('incluir_no_ecuatorianas') === '1') chips.push({ key: 'incluir_no_ecuatorianas', label: 'Incluye entidades no ecuatorianas' })
  return chips
}
