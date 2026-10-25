// Lista cerrada: solo catálogo y detalles numéricos. Sin dominios, query ni fragmentos.
export function safeReturnPath(value) {
  if (typeof value !== 'string' || value.length > 100) return '/inicio'
  const match = value.match(/^\/becas(?:\/[1-9][0-9]*)?$/)
  return match?.[0] === value ? value : '/inicio'
}

export function loginReturnPath(search) {
  const values = new URLSearchParams(search).getAll('next')
  return values.length === 1 ? safeReturnPath(values[0]) : '/inicio'
}
