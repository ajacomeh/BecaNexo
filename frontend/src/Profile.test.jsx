import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import AuthProvider from './auth/AuthProvider'

const user = { id: 1, nombre: 'Persona de prueba', email: 'perfil@example.com', rol: 'postulante' }
const catalogs = {
  paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }],
  idiomas: [{ id: 1, codigo: 'en', nombre: 'Inglés' }], areas: [{ id: 1, nombre: 'Informática' }],
  niveles: [{ valor: 'grado', nombre: 'Grado' }, { valor: 'maestria', nombre: 'Maestría' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }],
  niveles_idioma: [{ valor: 'B2', nombre: 'B2' }], estados: [{ valor: 'en_curso', nombre: 'En curso' }],
  dedicaciones: [{ valor: 'parcial', nombre: 'Tiempo parcial' }],
}
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
let profile, lists, fetchMock, failWrite, fieldErrors

function mount(path = '/perfil') {
  render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
}
beforeEach(() => {
  profile = { id: 1, nacionalidad: 1, residencia: null, ciudad_residencia: 'Quito', disponible_traslado: null, disponible_extranjero: null, version: 1 }
  lists = { formaciones: [], experiencias: [], idiomas: [], preferencias: [], areas: [], destinos: [] }
  failWrite = false; fieldErrors = null
  fetchMock = vi.fn(async (url, options = {}) => {
    if (url === '/api/auth/me/') return json(user)
    if (url === '/api/auth/csrf/') return json({ csrfToken: 'token-perfil' })
    if (url === '/api/perfil/catalogos/') return json(catalogs)
    const writing = options.method && options.method !== 'GET'
    if (writing && failWrite) throw new TypeError('network')
    if (writing && fieldErrors) return json(fieldErrors, 400)
    if (url === '/api/perfil/') {
      if (writing) profile = { ...profile, ...JSON.parse(options.body), version: (profile?.version || 0) + 1 }
      return json({ perfil: profile })
    }
    const resource = url.split('/')[3]
    if (options.method === 'POST') {
      const row = { id: 1, ...JSON.parse(options.body) }; lists[resource].push(row); return json(row, 201)
    }
    if (options.method === 'PATCH') {
      const row = { id: 1, ...JSON.parse(options.body) }; lists[resource] = [row]; return json(row)
    }
    if (options.method === 'DELETE') { lists[resource] = []; return new Response(null, { status: 204 }) }
    return json(lists[resource] || [])
  })
  vi.stubGlobal('fetch', fetchMock)
})

it('carga, edita y guarda el perfil propio con CSRF', async () => {
  mount()
  const city = await screen.findByLabelText('Ciudad de residencia')
  expect(city).toHaveValue('Quito')
  await userEvent.clear(city); await userEvent.type(city, 'Cuenca')
  await userEvent.selectOptions(screen.getByLabelText('País de residencia'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByText('Cambios guardados.')).toBeInTheDocument()
  expect(profile.ciudad_residencia).toBe('Cuenca')
  expect(profile.residencia).toBe(2)
  const [, request] = fetchMock.mock.calls.find(([url, options]) => url === '/api/perfil/' && options.method === 'PATCH')
  expect(request.headers['X-CSRFToken']).toBeTruthy()
  expect(JSON.parse(request.body)).not.toHaveProperty('usuario_id')
})

it('crea progresivamente antes de habilitar registros hijos', async () => {
  profile = null; mount()
  await screen.findByLabelText('Ciudad de residencia')
  expect(screen.queryByRole('button', { name: 'Añadir formación' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByRole('button', { name: 'Añadir formación' })).toBeInTheDocument()
})

it('conserva entradas y no anuncia guardado al fallar la red', async () => {
  mount()
  const city = await screen.findByLabelText('Ciudad de residencia')
  await userEvent.clear(city); await userEvent.type(city, 'Loja')
  failWrite = true
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No pudimos conectar')
  expect(city).toHaveValue('Loja')
  expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
  failWrite = false
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByText('Cambios guardados.')).toBeInTheDocument()
})

it('presenta el error del servidor junto al campo', async () => {
  mount()
  await screen.findByLabelText('Fecha de nacimiento')
  fieldErrors = { fecha_nacimiento: ['La fecha no puede ser futura.'] }
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByText('La fecha no puede ser futura.')).toBeInTheDocument()
  expect(screen.getByLabelText('Fecha de nacimiento')).toHaveAttribute('aria-invalid', 'true')
})

it('añade y edita una formación', async () => {
  mount()
  await userEvent.click(await screen.findByRole('button', { name: 'Añadir formación' }))
  const region = screen.getByRole('region', { name: 'Formación académica' })
  await userEvent.selectOptions(within(region).getByLabelText(/Nivel académico/), 'grado')
  await userEvent.selectOptions(within(region).getByLabelText(/Estado de estudios/), 'en_curso')
  await userEvent.type(within(region).getByLabelText(/Carrera/), 'Software')
  await userEvent.selectOptions(within(region).getByLabelText(/Título obtenido/), 'false')
  await userEvent.click(within(region).getByRole('button', { name: 'Guardar formación' }))
  await userEvent.click(await screen.findByRole('button', { name: /Editar formación: Software/ }))
  const career = within(region).getByLabelText(/Carrera/)
  expect(career).toHaveValue('Software')
  await userEvent.clear(career); await userEvent.type(career, 'Informática')
  await userEvent.click(within(region).getByRole('button', { name: 'Guardar formación' }))
  expect(await screen.findByText('Informática · En curso')).toBeInTheDocument()
})

it('gestiona idioma y nivel declarado sin certificados', async () => {
  mount('/preferencias')
  await userEvent.click(await screen.findByRole('button', { name: 'Añadir idioma' }))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Idioma', exact: true }), '1')
  await userEvent.selectOptions(screen.getByLabelText('Nivel declarado (MCER)'), 'B2')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar idioma' }))
  expect(await screen.findByText('Inglés · B2')).toBeInTheDocument()
  expect(document.querySelector('input[type="file"]')).toBeNull()
  expect(screen.getByText(/entidad oferente solicitará/)).toBeInTheDocument()
})

it('guarda preferencias y distingue sin declarar de no', async () => {
  mount('/preferencias')
  await userEvent.click(await screen.findByRole('button', { name: 'Añadir preferencia' }))
  await userEvent.selectOptions(screen.getByLabelText(/Nivel deseado/), 'maestria')
  await userEvent.selectOptions(screen.getByLabelText(/Modalidad deseada/), 'virtual')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar preferencia' }))
  expect(await screen.findByText('Maestría · Virtual')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('¿Puedes trasladarte?'), 'false')
  expect(screen.getByLabelText('¿Puedes estudiar en el extranjero?')).toHaveValue('')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar disponibilidad' }))
  await waitFor(() => expect(profile.disponible_traslado).toBe(false))
  expect(profile.disponible_extranjero).toBeNull()
})

it('administrador no accede al formulario ni recibe invitación', async () => {
  fetchMock.mockResolvedValueOnce(json({ ...user, rol: 'administrador' }))
  mount('/perfil')
  expect(await screen.findByRole('heading', { name: 'Hola, Persona de prueba' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Completar mi perfil' })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Ciudad de residencia')).not.toBeInTheDocument()
})

it('permite reintentar un fallo de carga', async () => {
  const original = fetchMock.getMockImplementation()
  let failed = false
  fetchMock.mockImplementation(async (url, options) => {
    if (url === '/api/perfil/' && !failed) { failed = true; throw new TypeError('network') }
    return original(url, options)
  })
  mount()
  await userEvent.click(await screen.findByRole('button', { name: 'Reintentar carga' }))
  expect(await screen.findByLabelText('Ciudad de residencia')).toHaveValue('Quito')
})
