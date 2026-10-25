export class ApiError extends Error {
  constructor(message, status = 0, fields = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
  }
}

let csrfToken = null

async function request(path, options = {}, prefix = 'auth', params = null) {
  let response
  try {
    response = await fetch(`/api/${prefix}/${path ? `${path}/` : ''}${params ? `?${new URLSearchParams(params)}` : ''}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      ...options,
      headers: { Accept: 'application/json', ...options.headers },
    })
  } catch {
    throw new ApiError('No pudimos conectar con BecaNexo. Revisa tu conexión e inténtalo de nuevo.')
  }
  let data = null
  if (response.status !== 204) {
    try { data = await response.json() } catch { /* No presentar HTML de errores del servidor. */ }
  }
  if (!response.ok) {
    if (response.status === 403) csrfToken = null
    if (response.status === 429) {
      const wait = Number(response.headers.get('Retry-After'))
      throw new ApiError(`Has realizado demasiados intentos. ${wait > 0 ? `Espera ${Math.ceil(wait)} segundos y vuelve a intentarlo.` : 'Espera un momento y vuelve a intentarlo.'}`, 429)
    }
    if (response.status >= 500) throw new ApiError('BecaNexo no está disponible en este momento. Inténtalo de nuevo más tarde.', response.status)
    if (response.status === 403) throw new ApiError('No se pudo verificar la sesión o la protección de la solicitud. Vuelve a intentarlo.', 403)
    const fields = data && typeof data === 'object' ? data : {}
    throw new ApiError(typeof fields.detail === 'string' ? fields.detail : 'Revisa los datos del formulario.', response.status, fields)
  }
  if (response.status !== 204 && (!data || typeof data !== 'object')) {
    throw new ApiError('Recibimos una respuesta inesperada del servidor.', 502)
  }
  return data
}

async function prepareCsrf() {
  const data = await request('csrf')
  if (typeof data.csrfToken !== 'string') throw new ApiError('No se pudo preparar la protección de la solicitud.', 502)
  csrfToken = data.csrfToken
}

async function post(path, data, freshToken = false) {
  if (freshToken || !csrfToken) await prepareCsrf()
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(data),
  })
}

export const authApi = {
  me: () => request('me'),
  register: (data) => post('registro', data, true),
  async login(data) {
    const result = await post('login', data, true)
    csrfToken = result.csrfToken
    return result.usuario
  },
  async logout() {
    await post('logout', {})
    csrfToken = null
  },
}

export const profileApi = {
  get: (path = '') => request(path, {}, 'perfil'),
  async write(path, method, data) {
    if (!csrfToken) await prepareCsrf()
    return request(path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    }, 'perfil')
  },
}

export const offersApi = {
  get: (path, params = {}) => request('', {}, path.replace(/\/$/, ''), params),
  async write(path, method, data = {}) {
    if (!csrfToken) await prepareCsrf()
    return request('', { method, headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }, body: JSON.stringify(data) }, path.replace(/\/$/, ''))
  },
}
