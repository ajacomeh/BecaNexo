import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import Offers from './pages/Offers'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { id: 1, nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

const BUSCAR = 'Buscar título, institución, área, descripción o programa'
const catalogs = {
  paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }],
  niveles: [{ valor: 'grado', nombre: 'Grado' }, { valor: 'maestria', nombre: 'Maestría' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }, { valor: 'presencial', nombre: 'Presencial' }],
  tipos_beca: [{ id: 3, nombre: 'Mérito' }, { id: 4, nombre: 'Socioeconómica' }], areas: [], idiomas: [], tipos_requisito: [],
}
const card = titulo => ({ id: 4, estado: 'borrador', titulo, institucion: { nombre: 'Entidad ficticia' }, beneficios: [], opciones: [], cierre: null })

function Location() { return <output data-testid="url">{useLocation().search}</output> }
function open(path = '/gestion/convocatorias', listing = params => ({ count: 1, page: 1, page_size: 12, results: [card(`Resultado ${params.q || params.estado || 'inicial'}`)] })) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (route, params = {}) => route === 'becas/catalogos' ? catalogs : listing(params))
  render(<MemoryRouter initialEntries={[path]}><Offers admin /><Location /></MemoryRouter>)
  return get
}
const consultas = get => get.mock.calls.filter(([route]) => route === 'gestion/convocatorias').map(([, params]) => params)

it('muestra buscador y una fila con Nivel, Modalidad, Destino, Tipo de beca y Estado, sin título, «Más filtros» ni «Aplicar filtros»', async () => {
  open()
  const filters = await screen.findByRole('search', { name: 'Filtros de convocatorias' })
  expect(within(filters).getByLabelText(BUSCAR)).toBeVisible()
  expect(within(filters).getAllByRole('combobox').map(select => select.labels[0].textContent)).toEqual(['Nivel', 'Modalidad', 'Destino de estudio', 'Tipo de beca', 'Estado'])
  expect(within(within(filters).getByLabelText('Tipo de beca')).getAllByRole('option').map(o => o.textContent)).toEqual(['Todos los tipos', 'Mérito', 'Socioeconómica'])
  expect(within(within(filters).getByLabelText('Estado')).getAllByRole('option').map(o => o.textContent))
    .toEqual(['Todos los estados', 'Borrador', 'Pausada', 'Abierta', 'Cerrada', 'Próxima apertura', 'Fecha de cierre no informada'])
  expect(screen.queryByRole('heading', { name: 'Filtros de búsqueda' })).not.toBeInTheDocument()
  expect(screen.queryByText('Más filtros')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Aplicar filtros' })).not.toBeInTheDocument()
  // Sin interruptor de entidades, destino rápido ni conteos: el listado del administrador no los admite.
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
  expect(within(within(filters).getByLabelText('Nivel')).getAllByRole('option').map(o => o.textContent)).toEqual(['Todos los niveles', 'Grado', 'Maestría'])
  // Se conservan la creación de convocatorias, el contador y el orden en una fila.
  expect(screen.getByRole('link', { name: 'Crear convocatoria' })).toHaveAttribute('href', '/gestion/convocatorias/nueva')
  const status = await screen.findByText('1 convocatorias encontradas')
  expect(status).toHaveAttribute('role', 'status')
  expect(status.parentElement).toContainElement(screen.getByLabelText('Ordenar por'))
})

it('la búsqueda se aplica a los 400 ms, vuelve a la página 1, queda en la URL y conserva el foco', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const get = open('/gestion/convocatorias?page=2&estado=pausada')
  const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  const search = await screen.findByLabelText(BUSCAR)
  await u.type(search, 'beca')
  act(() => { vi.advanceTimersByTime(300) })
  expect(consultas(get).some(p => p.q)).toBe(false)
  act(() => { vi.advanceTimersByTime(150) })
  await waitFor(() => expect(consultas(get).at(-1)).toEqual({ estado: 'pausada', q: 'beca' }))
  expect(screen.getByTestId('url').textContent).not.toContain('page=')
  expect(await screen.findByText('Resultado beca')).toBeVisible()
  expect(search).toHaveFocus()
})

it('Tipo de beca y Estado se aplican al cambiar y conservan el orden', async () => {
  const get = open('/gestion/convocatorias?orden=titulo&page=3')
  const u = userEvent.setup()
  await u.selectOptions(await screen.findByLabelText('Tipo de beca'), '4')
  expect(consultas(get).at(-1)).toEqual({ orden: 'titulo', tipo_beca: '4' })
  await u.selectOptions(screen.getByLabelText('Estado'), 'borrador')
  expect(consultas(get).at(-1)).toEqual({ orden: 'titulo', tipo_beca: '4', estado: 'borrador' })
  expect(screen.getByTestId('url')).toHaveTextContent(/^\?orden=titulo&tipo_beca=4&estado=borrador$/)
  expect(await screen.findByText('Resultado borrador')).toBeVisible()
})

it('solo la última consulta actualiza los resultados', async () => {
  const pending = {}
  open('/gestion/convocatorias', params => new Promise(resolve => { pending[params.estado || 'todos'] = resolve }))
  const u = userEvent.setup()
  await act(async () => { pending.todos({ count: 1, page: 1, page_size: 12, results: [card('Resultado inicial')] }) })
  await u.selectOptions(await screen.findByLabelText('Estado'), 'borrador')
  await u.selectOptions(screen.getByLabelText('Estado'), 'pausada')
  await act(async () => { pending.pausada({ count: 1, page: 1, page_size: 12, results: [card('Resultado pausada')] }) })
  await act(async () => { pending.borrador({ count: 1, page: 1, page_size: 12, results: [card('Resultado borrador')] }) })
  expect(await screen.findByText('Resultado pausada')).toBeVisible()
  expect(screen.queryByText('Resultado borrador')).not.toBeInTheDocument()
})

it('muestra fichas con botón para quitar cada filtro y «Limpiar todo» solo con filtros activos', async () => {
  open('/gestion/convocatorias?q=salud&nivel=maestria&destino=ES&tipo_beca=3&estado=cerrada&orden=cierre')
  const u = userEvent.setup()
  const chips = await screen.findByRole('list', { name: 'Filtros activos' })
  expect(within(chips).getAllByRole('listitem').map(li => li.textContent))
    .toEqual(['Búsqueda: «salud»', 'Nivel: Maestría', 'Destino: España', 'Tipo de beca: Mérito', 'Estado: Cerrada'])
  await u.click(screen.getByRole('button', { name: 'Quitar filtro Estado: Cerrada' }))
  expect(screen.getByTestId('url').textContent).not.toContain('estado=')
  expect(screen.getByLabelText('Estado')).toHaveValue('')
  expect(screen.getByLabelText(BUSCAR)).toHaveFocus()
  await u.click(screen.getByRole('button', { name: 'Limpiar todo' }))
  expect(screen.getByTestId('url')).toHaveTextContent(/^\?orden=cierre$/)
  expect(screen.getByLabelText(BUSCAR)).toHaveValue('')
  expect(screen.queryByRole('button', { name: 'Limpiar todo' })).not.toBeInTheDocument()
})

it('en móvil «Filtros (n)» indica los filtros activos y despliega los controles', async () => {
  open('/gestion/convocatorias?estado=borrador&tipo_beca=3')
  const u = userEvent.setup()
  const toggle = await screen.findByRole('button', { name: 'Filtros (2)' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  const controls = document.getElementById(toggle.getAttribute('aria-controls'))
  expect(controls).toContainElement(screen.getByLabelText('Estado'))
  await u.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
})
