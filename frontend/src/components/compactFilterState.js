// Estado de los filtros compactos, compartido por el catálogo público y la gestión de convocatorias del administrador.
import { readable } from '../pages/catalogPresentation'

export const PUBLIC_FILTER_KEYS = ['q', 'nivel', 'modalidad', 'destino', 'destino_ambito', 'tipo_beca', 'incluir_no_ecuatorianas']
export const ADMIN_FILTER_KEYS = ['q', 'nivel', 'modalidad', 'destino', 'tipo_beca', 'estado']
export const ADMIN_STATES = ['borrador', 'pausada', 'abierta', 'cerrada', 'proxima', 'sin_fecha']
export const AMBITOS = [['', 'Todos'], ['ecuador', 'Ecuador'], ['exterior', 'Extranjero']]

export const stateName = value => ({ todas: 'Todas las publicadas', vigentes: 'Vigentes', proxima: 'Próxima apertura',
  cierre_hoy: 'Cierra hoy; hora no informada', sin_fecha: 'Fecha de cierre no informada' }[value] || readable(value))

// Una ficha por filtro aplicado, en el orden de los controles; solo las de los parámetros que admite la pantalla.
export function activeFilters(params, catalogs, keys = PUBLIC_FILTER_KEYS) {
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
  if (params.get('estado')) chips.push({ key: 'estado', label: `Estado: ${stateName(params.get('estado'))}` })
  if (params.get('incluir_no_ecuatorianas') === '1') chips.push({ key: 'incluir_no_ecuatorianas', label: 'Incluye entidades no ecuatorianas' })
  return chips.filter(chip => keys.includes(chip.key))
}
