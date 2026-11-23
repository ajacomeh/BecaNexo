// Estado de una ejecución de rastreo en lenguaje de administración. El dominio conserva «finalizada»;
// «Parcial» se reserva para fallos reales (red, HTTP inesperado ≥ 400, análisis o extracción). Los avisos
// por diseño (tope de fichas, bases fuera de la lista cerrada, rotación del índice) no degradan el estado.
const estados = {
  finalizada: 'Completada',
  parcial: 'Parcial: hubo fallos de red, HTTP o análisis',
  fallida: 'Fallida',
  en_curso: 'En curso',
  omitida: 'Omitida',
}

export function estadoEjecucion(estado, avisos = 0) {
  if (estado === 'finalizada' && avisos > 0) return 'Completada con avisos'
  return estados[estado] || String(estado ?? '').replaceAll('_', ' ')
}
