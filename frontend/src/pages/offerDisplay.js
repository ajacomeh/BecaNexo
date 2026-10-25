export const display = (value) => value == null || value === '' ? 'No especificado' : String(value)
export const date = (value) => value ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Guayaquil' }).format(new Date(value)) : 'No especificado'
export const stateLabel = (value) => ({ abierta: 'Abierta', cerrada: 'Cerrada', proxima: 'Próxima apertura', sin_fecha: 'Cierre no especificado', borrador: 'Borrador', pausada: 'Pausada' }[value] || value)
