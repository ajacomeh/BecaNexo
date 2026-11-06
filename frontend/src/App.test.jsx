import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import AuthProvider from './auth/AuthProvider'

const account = { id: 1, email: 'prueba@example.com', nombre: 'Persona de prueba', rol: 'postulante' }
const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
})
let fetchMock
function mount(path = '/login') {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
}
async function registerFields() {
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Nombre completo'), 'Persona de prueba')
  await user.type(screen.getByLabelText('Correo electrónico'), account.email)
  await user.type(screen.getByLabelText('Contraseña'), 'Clave-Solo-Pruebas!726')
  await user.type(screen.getByLabelText('Confirmar contraseña'), 'Clave-Solo-Pruebas!726')
  return user
}
beforeEach(() => {
  fetchMock = vi.fn(async (url) => {
    if (url.endsWith('/me/')) return json({ detail: 'Sin sesión' }, 403)
    if (url.endsWith('/csrf/')) return json({ csrfToken: 'csrf-prueba' })
    throw new Error('Solicitud no simulada en la prueba')
  })
  vi.stubGlobal('fetch', fetchMock)
})

describe('Navegación y sesión', () => {
  it('espera me antes de mostrar la página protegida', async () => {
    let resolve
    fetchMock.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    mount('/inicio')
    expect(screen.getByRole('status')).toHaveTextContent('Comprobando tu sesión')
    expect(screen.queryByRole('heading', { name: 'Inicia sesión' })).not.toBeInTheDocument()
    await act(async () => resolve(json(account)))
    expect(await screen.findByRole('heading', { name: `Hola, ${account.nombre}` })).toBeInTheDocument()
    expect(screen.getByText('postulante')).toBeInTheDocument()
  })
  it('redirige anónimos a login', async () => {
    mount('/inicio')
    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
  })
  it.each(['red', 'servidor'])('distingue fallo de %s en me y permite reintentar', async (kind) => {
    if (kind === 'red') fetchMock.mockRejectedValueOnce(new TypeError('Network error'))
    else fetchMock.mockResolvedValueOnce(json({}, 503))
    mount('/inicio')
    expect(await screen.findByRole('heading', { name: 'No pudimos comprobar tu sesión' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Contraseña')).not.toBeInTheDocument()
    fetchMock.mockResolvedValueOnce(json(account))
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar conexión' }))
    expect(await screen.findByRole('heading', { name: `Hola, ${account.nombre}` })).toBeInTheDocument()
  })
  it('cierra sesión y maneja 204 sin JSON', async () => {
    fetchMock.mockResolvedValueOnce(json(account))
    const noContent = new Response(null, { status: 204 })
    const parse = vi.spyOn(noContent, 'json')
    mount('/inicio')
    await screen.findByRole('heading', { name: `Hola, ${account.nombre}` })
    fetchMock.mockImplementation(async (url) => url.endsWith('/csrf/') ? json({ csrfToken: 'logout-token' }) : noContent)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
    expect(parse).not.toHaveBeenCalled()
    expect(fetchMock.mock.calls.find(([url]) => url.endsWith('/logout/'))[1].headers['X-CSRFToken']).toBeTruthy()
  })
})

describe('Registro', () => {
  it('registra con CSRF y dirige al login sin autenticación automática', async () => {
    mount('/registro')
    const user = await registerFields()
    fetchMock.mockImplementation(async (url) => url.endsWith('/csrf/') ? json({ csrfToken: 'nuevo-token' }) : json(account, 201))
    await user.click(screen.getByRole('button', { name: 'Crear mi cuenta' }))
    expect(await screen.findByText('Tu cuenta fue creada. Ya puedes iniciar sesión.')).toBeInTheDocument()
    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/registro/'))
    expect(options.headers['X-CSRFToken']).toBe('nuevo-token')
    expect(options.credentials).toBe('same-origin')
    expect(Object.keys(JSON.parse(options.body))).toEqual(['nombre', 'email', 'password', 'password_confirm'])
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/login/'))).toBe(false)
  })
  it('presenta errores de validación devueltos por Django', async () => {
    mount('/registro')
    const user = await registerFields()
    fetchMock.mockImplementation(async (url) => url.endsWith('/csrf/') ? json({ csrfToken: 'nuevo-token' }) : json({ email: ['No se puede registrar este correo.'], password: ['Esta contraseña es demasiado común.'] }, 400))
    await user.click(screen.getByRole('button', { name: 'Crear mi cuenta' }))
    expect(await screen.findByText('No se puede registrar este correo.')).toBeInTheDocument()
    expect(screen.getByLabelText('Correo electrónico')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Esta contraseña es demasiado común.')).toBeInTheDocument()
  })
  it('valida confirmación y evita enviar campos incompletos', async () => {
    mount('/registro')
    const user = await registerFields()
    await user.clear(screen.getByLabelText('Confirmar contraseña'))
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Otra')
    await user.click(screen.getByRole('button', { name: 'Crear mi cuenta' }))
    expect(screen.getByText('Las contraseñas no coinciden.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/registro/'))).toBe(false)
  })
  it('bloquea envíos duplicados mientras espera respuesta', async () => {
    mount('/registro')
    const user = await registerFields()
    let finish
    fetchMock.mockImplementation(async (url) => url.endsWith('/csrf/') ? json({ csrfToken: 'nuevo-token' }) : new Promise((resolve) => { finish = resolve }))
    await user.dblClick(screen.getByRole('button', { name: 'Crear mi cuenta' }))
    await waitFor(() => expect(finish).toBeDefined())
    expect(screen.getByRole('button', { name: 'Creando tu cuenta…' })).toBeDisabled()
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/registro/'))).toHaveLength(1)
    await act(async () => finish(json(account, 201)))
  })
})

describe('Login y errores de API', () => {
  async function fillLogin() {
    mount()
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Correo electrónico'), account.email)
    await user.type(screen.getByLabelText('Contraseña'), 'Clave-Solo-Pruebas!726')
    return user
  }
  it('obtiene un token CSRF reciente antes de cerrar sesión', async () => {
    const user = await fillLogin()
    let csrfRequests = 0
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/csrf/')) return json({ csrfToken: ++csrfRequests === 1 ? 'token-inicial' : 'token-final' })
      if (url.endsWith('/login/')) return json({ usuario: account, csrfToken: 'token-renovado' })
      return new Response(null, { status: 204 })
    })
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await screen.findByRole('heading', { name: 'Inicia sesión' })
    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith('/logout/'))
    expect(options.headers['X-CSRFToken']).toBe('token-final')
    expect(csrfRequests).toBe(2)
  })
  it('sale de la interfaz autenticada si la sesión del servidor caducó y permite otra cuenta', async () => {
    fetchMock.mockResolvedValueOnce(json(account))
    mount('/inicio')
    await screen.findByRole('heading', { name: `Hola, ${account.nombre}` })
    const admin = { ...account, id: 2, email: 'admin@example.com', nombre: 'Admin de prueba', rol: 'administrador' }
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/csrf/')) return json({ csrfToken: 'token-reciente' })
      if (url.endsWith('/logout/') || url.endsWith('/me/')) return json({ detail: 'Sin sesión' }, 403)
      if (url.endsWith('/login/')) return json({ usuario: admin, csrfToken: 'token-admin' })
      throw new Error('Solicitud no simulada')
    })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/logout/'))).toBe(true)
    await user.type(screen.getByLabelText('Correo electrónico'), admin.email)
    await user.type(screen.getByLabelText('Contraseña'), 'Clave-Solo-Pruebas!726')
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findByRole('heading', { name: `Hola, ${admin.nombre}` })).toBeInTheDocument()
  })
  it('conserva la sesión local si logout falla por CSRF pero me sigue autenticado', async () => {
    fetchMock.mockResolvedValueOnce(json(account))
    mount('/inicio')
    await screen.findByRole('heading', { name: `Hola, ${account.nombre}` })
    fetchMock.mockImplementation(async (url) => {
      if (url.endsWith('/csrf/')) return json({ csrfToken: 'token-reciente' })
      if (url.endsWith('/logout/')) return json({ detail: 'CSRF incorrecto' }, 403)
      if (url.endsWith('/me/')) return json(account)
      throw new Error('Solicitud no simulada')
    })
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo verificar la sesión')
    expect(screen.getByRole('heading', { name: `Hola, ${account.nombre}` })).toBeInTheDocument()
  })
  it.each([403, 429, 500])('presenta un error controlado para %s', async (status) => {
    const user = await fillLogin()
    fetchMock.mockImplementation(async (url) => url.endsWith('/csrf/') ? json({ csrfToken: 'token' }) : json({}, status, { 'Retry-After': '12' }))
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toMatch(status === 429 ? /12 segundos/ : status === 403 ? /protección/ : /no está disponible/)
    expect(screen.getByRole('button', { name: 'Iniciar sesión' })).not.toBeDisabled()
  })
})
