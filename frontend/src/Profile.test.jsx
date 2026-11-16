import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import AuthProvider from './auth/AuthProvider'
import { authApi } from './api/client'

const user = { id: 1, nombre: 'Persona de prueba', email: 'perfil@example.com', rol: 'postulante' }
const catalogs = {
  paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }],
  idiomas: [{ id: 1, codigo: 'en', nombre: 'Inglés' }], areas: [{ id: 1, nombre: 'Informática' }],
  niveles: [{ valor: 'grado', nombre: 'Grado' }, { valor: 'maestria', nombre: 'Maestría' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }, { valor: 'hibrida', nombre: 'Híbrida' }],
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

it.each([
  ['/perfil#datos-personales', 'Datos personales y residencia'],
  ['/perfil#formacion-academica', 'Formación académica'],
  ['/perfil#experiencia', 'Experiencia relevante'],
  ['/preferencias#idiomas', 'Idiomas declarados'],
  ['/preferencias#preferencias', 'Preferencias de estudio'],
  ['/preferencias#disponibilidad', 'Disponibilidad declarada'],
])('enfoca el apartado solicitado al abrir %s', async (path, title) => {
  mount(path)
  const heading = await screen.findByRole('heading', { name: title })
  await waitFor(() => expect(heading).toHaveFocus())
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
  expect(JSON.parse(request.body)).not.toHaveProperty('nombre')
})

it('guarda el nombre en la cuenta, actualiza barra lateral y lo recupera al volver', async () => {
  let nombre = user.nombre
  const original = fetchMock.getMockImplementation()
  fetchMock.mockImplementation((url, options = {}) => {
    if (url === '/api/auth/me/') {
      if (options.method === 'PATCH') nombre = JSON.parse(options.body).nombre
      return Promise.resolve(json(options.method === 'PATCH' ? { nombre } : { ...user, nombre }))
    }
    return original(url, options)
  })
  const view = render(<MemoryRouter initialEntries={['/perfil']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  const field = await screen.findByLabelText(/^Nombre visible/)
  expect(screen.queryByRole('button', { name: 'Editar nombre' })).not.toBeInTheDocument()
  await userEvent.clear(field)
  await userEvent.type(field, 'María <b>José</b>')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(screen.getByText('María <b>José</b>', { selector: '.sidebar-name span' })).toBeVisible()
  expect(profile).not.toHaveProperty('nombre')
  expect(document.querySelector('b')).toBeNull()
  view.unmount(); mount()
  expect(await screen.findByLabelText(/^Nombre visible/)).toHaveValue(nombre)
  const calls = () => fetchMock.mock.calls.filter(([url, options]) => url === '/api/auth/me/' && options?.method === 'PATCH')
  expect(calls()).toHaveLength(1)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(calls()).toHaveLength(1)
})

it('informa guardado parcial y conserva nombre pendiente al fallar la cuenta', async () => {
  const save = vi.spyOn(authApi, 'updateName').mockRejectedValueOnce(new Error('Fallo de cuenta')).mockResolvedValue({ nombre: 'Nuevo' })
  mount()
  const field = await screen.findByLabelText(/^Nombre visible/)
  await userEvent.clear(field); await userEvent.type(field, 'Nuevo')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Los datos del perfil se guardaron, pero el nombre no pudo guardarse')
  expect(field).toHaveValue('Nuevo')
  expect(screen.getByText(user.nombre, { selector: '.sidebar-name span' })).toBeVisible()
  expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(save).toHaveBeenCalledTimes(2)
  expect(screen.getByText('Nuevo', { selector: '.sidebar-name span' })).toBeVisible()
})

it('conserva cambios y no actualiza nombre si falla el perfil; rechaza nombre vacío', async () => {
  const save = vi.spyOn(authApi, 'updateName')
  mount()
  const field = await screen.findByLabelText(/^Nombre visible/)
  await userEvent.clear(field)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(screen.getByText('El nombre no puede estar vacío.')).toBeVisible()
  expect(save).not.toHaveBeenCalled()
  await userEvent.type(field, 'Pendiente')
  failWrite = true
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByRole('alert')
  expect(field).toHaveValue('Pendiente')
  expect(save).not.toHaveBeenCalled()
  expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
})

it('crea progresivamente antes de habilitar registros hijos', async () => {
  profile = null; mount()
  await screen.findByLabelText('Ciudad de residencia')
  await userEvent.selectOptions(screen.getByLabelText(/^Nacionalidad/), '1')
  expect(screen.queryByRole('button', { name: 'Añadir formación' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(await screen.findByRole('button', { name: 'Añadir formación' })).toBeInTheDocument()
})

it('guarda, recupera, edita y vacía Sobre mi perfil como texto con contador y límite', async () => {
  const view = render(<MemoryRouter initialEntries={['/perfil']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  const input = await screen.findByLabelText('Sobre mi perfil')
  expect(input).toHaveValue('')
  expect(input).toHaveAttribute('maxlength', '1500')
  expect(screen.getByText('0 / 1500 caracteres')).toBeVisible()
  await userEvent.type(input, '<b>Estudios</b>')
  expect(screen.getByText('15 / 1500 caracteres')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  view.unmount()
  mount()
  const recovered = await screen.findByLabelText('Sobre mi perfil')
  expect(recovered).toHaveValue('<b>Estudios</b>')
  expect(recovered.querySelector('b')).toBeNull()
  await userEvent.clear(recovered)
  await userEvent.type(recovered, 'Objetivos')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(profile.descripcion).toBe('Objetivos')
  await userEvent.clear(recovered)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(profile.descripcion).toBeNull()
})

it('exige nacionalidad explícita y rechaza otro país sin cambiar residencia', async () => {
  profile = null
  mount()
  const nationality = await screen.findByLabelText(/^Nacionalidad/)
  expect(nationality).toHaveValue('')
  expect(within(nationality).getByRole('option', { name: 'Selecciona tu nacionalidad' })).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(profile).toBeNull()
  await userEvent.selectOptions(nationality, '2')
  expect(screen.getByText('Actualmente BecaNexo está disponible únicamente para ciudadanos ecuatorianos')).toBeVisible()
  expect(nationality).toHaveValue('')
  await userEvent.selectOptions(nationality, '1')
  await userEvent.selectOptions(screen.getByLabelText('País de residencia'), '2')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(profile).toMatchObject({ nacionalidad: 1, residencia: 2 })
  await userEvent.selectOptions(nationality, '2')
  expect(nationality).toHaveValue('1')
})

it('conserva la nacionalidad guardada y usa código EC con ID no fijo', async () => {
  const get = fetchMock.getMockImplementation()
  fetchMock.mockImplementation((url, options) => url === '/api/perfil/catalogos/' ? Promise.resolve(json({ ...catalogs, paises: [{ id: 99, codigo: 'EC', nombre: 'Ecuador' }, catalogs.paises[1]] })) : get(url, options))
  profile.nacionalidad = 99
  mount()
  expect(await screen.findByLabelText(/^Nacionalidad/)).toHaveValue('99')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  await screen.findByText('Cambios guardados.')
  expect(profile.nacionalidad).toBe(99)
})

it('informa falta de Ecuador sin guardar ni asignar otro país', async () => {
  const get = fetchMock.getMockImplementation()
  fetchMock.mockImplementation((url, options) => url === '/api/perfil/catalogos/' ? Promise.resolve(json({ ...catalogs, paises: [catalogs.paises[1]] })) : get(url, options))
  profile = null
  mount()
  await screen.findByLabelText(/^Nacionalidad/)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar datos personales' }))
  expect(screen.getByText('Falta Ecuador en el catálogo de países. No es posible confirmar la nacionalidad.')).toBeVisible()
  expect(profile).toBeNull()
})

it('limpia el fin al marcar trabajo actual y conserva null al guardar y consultar de nuevo', async () => {
  const view = render(<MemoryRouter initialEntries={['/perfil']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: 'Añadir experiencia' }))
  const start = screen.getByLabelText(/^Fecha de inicio/)
  const end = screen.getByLabelText('Fecha final')
  const current = screen.getByRole('checkbox', { name: 'Actualmente trabajo aquí' })
  await userEvent.type(start, '2020-01-01')
  await userEvent.type(end, '2021-01-01')
  await userEvent.click(current)
  expect(end).toHaveValue('')
  expect(end).toBeDisabled()
  expect(end).toHaveAccessibleDescription('No corresponde mientras continúes trabajando')
  expect(start).toBeEnabled()
  expect(start).toHaveValue('2020-01-01')
  await userEvent.click(current)
  expect(end).toBeEnabled()
  expect(end).toHaveValue('')
  await userEvent.click(current)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar experiencia' }))
  await screen.findByText('Cambios guardados.')
  const [, request] = fetchMock.mock.calls.find(([url, options]) => url === '/api/perfil/experiencias/' && options.method === 'POST')
  expect(JSON.parse(request.body)).toMatchObject({ actual: true, fecha_fin: null, fecha_inicio: '2020-01-01' })
  view.unmount()
  mount()
  await userEvent.click(await screen.findByRole('button', { name: /^Editar experiencia:/ }))
  expect(screen.getByRole('checkbox', { name: 'Actualmente trabajo aquí' })).toBeChecked()
  expect(screen.getByLabelText('Fecha final')).toHaveValue('')
  expect(screen.getByLabelText('Fecha final')).toBeDisabled()
  expect(screen.getByLabelText(/^Fecha de inicio/)).toBeEnabled()
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

it('permite declarar Híbrida sin exigir cambios a preferencias anteriores', async () => {
  mount('/preferencias')
  await userEvent.click(await screen.findByRole('button', { name: 'Añadir preferencia' }))
  await userEvent.selectOptions(screen.getByLabelText(/Nivel deseado/), 'grado')
  await userEvent.selectOptions(screen.getByLabelText(/Modalidad deseada/), 'hibrida')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar preferencia' }))
  expect(await screen.findByText('Grado · Híbrida')).toBeInTheDocument()
  expect(lists.preferencias[0].modalidad).toBe('hibrida')
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
