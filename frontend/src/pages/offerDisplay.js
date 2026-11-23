// Oferente visible: entidad del catálogo o, sin ella, el oferente detectado en la ficha (texto, no ecuatoriano o por confirmar).
export function providerLabel(offer, { detailed = false } = {}) {
  if (offer.institucion?.nombre) return detailed ? `${offer.institucion.nombre} · Entidad oferente ecuatoriana` : offer.institucion.nombre
  const external = offer.oferente_externo
  if (external?.no_ecuatoriano && external.nombre) return `Oferente: ${external.nombre} (no ecuatoriano)`
  if (external) return 'Oferente por confirmar'
  return detailed ? 'Entidad oferente: No identificada · Consulta la fuente oficial' : 'Entidad oferente: No identificada'
}
export const display = (value) => value == null || value === '' ? 'No especificado' : String(value)
export const date = (value) => value ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Guayaquil' }).format(new Date(value)) : 'No especificado'
export const dayDate = (value) => value ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`)) : 'No especificado'

const months = { enero: '01', febrero: '02', marzo: '03', abril: '04', mayo: '05', junio: '06', julio: '07', agosto: '08', septiembre: '09', octubre: '10', noviembre: '11', diciembre: '12' }
export function publishedPeriod(offer) {
  const match = offer.cierre_original?.trim().toLocaleLowerCase('es').match(/^(?:del\s+)?(\d{1,2}) de ([a-záéíóú]+) al (\d{1,2}) de ([a-záéíóú]+) de (\d{4})$/u)
  if (!match || !months[match[2]] || !months[match[4]]) return null
  const start = `${match[5]}-${months[match[2]]}-${match[1].padStart(2, '0')}`
  const end = `${match[5]}-${months[match[4]]}-${match[3].padStart(2, '0')}`
  const valid = value => !Number.isNaN(Date.parse(`${value}T12:00:00Z`)) && new Date(`${value}T12:00:00Z`).toISOString().startsWith(value)
  if (!valid(start) || !valid(end) || start > end || offer.cierre_dia !== end) return null
  return { start, end }
}
export const stateLabel = (value) => ({ abierta: 'Abierta', cerrada: 'Cerrada', cierre_hoy: 'Cierra hoy · hora no informada', proxima: 'Próxima apertura', sin_fecha: 'Cierre no especificado', borrador: 'Borrador', pausada: 'Pausada' }[value] || value)
export const closingText = (offer, compact = false) => offer.cierre
  ? compact ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeZone: 'America/Guayaquil' }).format(new Date(offer.cierre)) : date(offer.cierre)
  : offer.cierre_dia
    ? `${dayDate(offer.cierre_dia)} · hora no informada`
    : offer.cierre_original?.trim() || 'Fecha de cierre no informada'
