import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import PublicCatalog from './pages/PublicCatalog'
import Offers from './pages/Offers'

const auth = vi.hoisted(() => ({ user: null }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: auth.user, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); auth.user = null })

const BUSCAR = 'Buscar título, institución, área, descripción o programa'
const catalogs = {
  paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }, { id: 3, codigo: 'JP', nombre: 'Japón' }],
  niveles: [{ valor: 'grado', nombre: 'Grado' }, { valor: 'maestria', nombre: 'Maestría' }, { valor: 'doctorado', nombre: 'Doctorado' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }, { valor: 'presencial', nombre: 'Presencial' }],
  tipos_beca: [{ id: 1, nombre: 'Mérito' }], areas: [], idiomas: [], tipos_requisito: [],
}
const facetas = {
  nivel: [{ valor: 'grado', total: 4 }, { valor: 'maestria', total: 2 }],
  modalidad: [{ valor: 'presencial', total: 5 }],
  destino: [{ valor: 'EC', total: 4 }, { valor: 'ES', total: 2 }],
  destino_ambito: { ecuador: 4, exterior: 2 },
}
const offer = { id: 1, titulo: 'Beca sintética', institucion: { nombre: 'Entidad' }, estado: 'abierta', beneficios: [], opciones: [] }

function Location() { return <output data-testid="url">{useLocation().search}</output> }
function open(path = '/becas', response = params => ({ count: 1, page: 1, page_size: 12, results: [{ ...offer, titulo: `Resultado ${params.q || 'inicial'}` }], facetas })) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (route, params = {}) => route === 'becas/catalogos' ? catalogs : response(params))
  render(<MemoryRouter initialEntries={[path]}><PublicCatalog /><Location /></MemoryRouter>)
  return get
}
const consultas = get => get.mock.calls.filter(([route]) => route === 'becas').map(([, params]) => params)

it('la búsqueda se aplica al dejar de escribir (400 ms), reinicia la página y conserva el foco', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const get = open('/becas?page=3&nivel=grado')
  const u = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
  const search = await screen.findByLabelText(BUSCAR)
  await u.type(search, 'beca')
  act(() => { vi.advanceTimersByTime(300) })
  expect(consultas(get).some(p => p.q)).toBe(false)
  act(() => { vi.advanceTimersByTime(150) })
  await waitFor(() => expect(consultas(get).at(-1)).toEqual({ nivel: 'grado', q: 'beca' }))
  expect(screen.getByTestId('url').textContent).not.toContain('page=')
  expect(consultas(get).filter(p => p.q)).toHaveLength(1)
  expect(search).toHaveFocus()
  expect(await screen.findByText('Resultado beca')).toBeVisible()
  expect(search).toHaveFocus()
})

it('Enter aplica la búsqueda sin esperar', async () => {
  const get = open()
  const u = userEvent.setup()
  await u.type(await screen.findByLabelText(BUSCAR), 'medicina{Enter}')
  expect(consultas(get).at(-1)).toEqual({ q: 'medicina' })
  expect(screen.queryByRole('button', { name: 'Aplicar filtros' })).not.toBeInTheDocument()
})

it('solo la última consulta actualiza los resultados aunque una anterior responda después', async () => {
  const pending = {}
  open('/becas', params => new Promise(resolve => { pending[params.nivel || 'todos'] = resolve }))
  const u = userEvent.setup()
  await u.selectOptions(await screen.findByLabelText('Nivel'), 'grado')
  await u.selectOptions(screen.getByLabelText('Nivel'), 'maestria')
  await act(async () => { pending.maestria({ count: 1, page: 1, page_size: 12, results: [{ ...offer, titulo: 'Resultado maestría' }], facetas }) })
  await act(async () => { pending.grado({ count: 1, page: 1, page_size: 12, results: [{ ...offer, titulo: 'Resultado grado' }], facetas }) })
  expect(await screen.findByText('Resultado maestría')).toBeVisible()
  expect(screen.queryByText('Resultado grado')).not.toBeInTheDocument()
})

it('muestra una ficha por filtro activo, la quita con su botón y «Limpiar todo» solo aparece con filtros', async () => {
  open('/becas?estado=cerrada&nivel=maestria&modalidad=presencial&q=salud&incluir_no_ecuatorianas=1&orden=titulo')
  const u = userEvent.setup()
  const chips = await screen.findByRole('list', { name: 'Filtros activos' })
  expect(within(chips).getAllByRole('listitem').map(li => li.textContent)).toEqual(
    ['Búsqueda: «salud»', 'Nivel: Maestría', 'Modalidad: Presencial', 'Incluye entidades no ecuatorianas'])
  await u.click(screen.getByRole('button', { name: 'Quitar filtro Nivel: Maestría' }))
  expect(screen.getByTestId('url').textContent).not.toContain('nivel=')
  expect(screen.getByLabelText('Nivel')).toHaveValue('')
  expect(screen.getByLabelText(BUSCAR)).toHaveFocus()
  await u.click(screen.getByRole('button', { name: 'Quitar filtro Búsqueda: «salud»' }))
  expect(screen.getByLabelText(BUSCAR)).toHaveValue('')
  await u.click(screen.getByRole('button', { name: 'Limpiar todo' }))
  // Conserva la pestaña y el orden.
  expect(screen.getByTestId('url')).toHaveTextContent(/^\?estado=cerrada&orden=titulo$/)
  expect(screen.queryByRole('list', { name: 'Filtros activos' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Limpiar todo' })).not.toBeInTheDocument()
  expect(screen.getByRole('switch', { name: 'Incluir entidades no ecuatorianas' })).not.toBeChecked()
})

it('el interruptor tiene ayuda accesible, se aplica al cambiar y se refleja en la URL', async () => {
  const get = open('/becas?estado=proxima')
  const u = userEvent.setup()
  const toggle = await screen.findByRole('switch', { name: 'Incluir entidades no ecuatorianas' })
  expect(toggle).toHaveAccessibleDescription('Por defecto se muestran solo becas de entidades ecuatorianas.')
  await u.click(toggle)
  expect(consultas(get).at(-1)).toEqual({ estado: 'proxima', incluir_no_ecuatorianas: '1' })
  expect(screen.getByTestId('url')).toHaveTextContent('incluir_no_ecuatorianas=1')
})

it('el destino rápido usa destino_ambito y se excluye con el país concreto', async () => {
  const get = open('/becas?destino=ES')
  const u = userEvent.setup()
  const group = await screen.findByRole('radiogroup', { name: 'Destino rápido' })
  expect(within(group).getByRole('radio', { name: 'Todos' })).toBeChecked()
  await u.click(within(group).getByRole('radio', { name: 'Extranjero (2)' }))
  expect(consultas(get).at(-1)).toEqual({ destino_ambito: 'exterior' })
  expect(screen.getByLabelText('Destino de estudio')).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Quitar filtro Destino: Extranjero' })).toBeVisible()
  await u.selectOptions(screen.getByLabelText('Destino de estudio'), 'EC')
  expect(consultas(get).at(-1)).toEqual({ destino: 'EC' })
  expect(within(group).getByRole('radio', { name: 'Todos' })).toBeChecked()
  await u.click(within(group).getByRole('radio', { name: 'Ecuador (4)' }))
  expect(consultas(get).at(-1)).toEqual({ destino_ambito: 'ecuador' })
  await u.click(within(group).getByRole('radio', { name: 'Todos' }))
  expect(consultas(get).at(-1)).toEqual({})
})

it('los selectores muestran solo valores presentes con su número de resultados y conservan el elegido', async () => {
  open('/becas?nivel=doctorado')
  const options = label => within(screen.getByLabelText(label)).getAllByRole('option').map(o => o.textContent)
  await screen.findByText('Resultado inicial')
  expect(options('Nivel')).toEqual(['Todos los niveles', 'Grado (4)', 'Maestría (2)', 'Doctorado (0)'])
  expect(options('Modalidad')).toEqual(['Todas las modalidades', 'Presencial (5)'])
  expect(options('Destino de estudio')).toEqual(['Todos los destinos', 'Ecuador (4)', 'España (2)'])
})

it('no muestra «Tipo de beca» ni «Más filtros» en el catálogo público', async () => {
  open()
  await screen.findByRole('search', { name: 'Filtros del catálogo' })
  expect(screen.queryByLabelText('Tipo de beca')).not.toBeInTheDocument()
  expect(screen.queryByText('Más filtros')).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Filtros de búsqueda' })).not.toBeInTheDocument()
})

it('el contador y «Ordenar por» van en la fila de las pestañas', async () => {
  open()
  const status = await screen.findByText('1 convocatoria encontrada')
  expect(status).toHaveAttribute('role', 'status')
  const toolbar = screen.getByRole('group', { name: 'Vigencia de las becas' }).parentElement
  expect(toolbar).toContainElement(status)
  expect(toolbar).toContainElement(screen.getByLabelText('Ordenar por'))
})

it('en móvil el botón «Filtros (n)» indica los filtros activos y despliega los controles', async () => {
  open('/becas?nivel=grado&modalidad=presencial')
  const u = userEvent.setup()
  const toggle = await screen.findByRole('button', { name: 'Filtros (2)' })
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
  const controls = document.getElementById(toggle.getAttribute('aria-controls'))
  expect(controls).toContainElement(screen.getByLabelText('Nivel'))
  expect(controls).not.toContainElement(screen.getByLabelText(BUSCAR))
  await u.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(controls).toHaveClass('is-open')
})

it('la gestión de convocatorias usa su propia configuración del filtro compacto', async () => {
  auth.user = { id: 1, nombre: 'Admin', rol: 'administrador' }
  vi.spyOn(offersApi, 'get').mockImplementation(async route => route === 'becas/catalogos' ? catalogs : { count: 0, page: 1, page_size: 12, results: [] })
  render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
  expect(await screen.findByRole('search', { name: 'Filtros de convocatorias' })).toBeVisible()
  expect(screen.getByLabelText('Tipo de beca')).toBeVisible()
  expect(screen.getByLabelText('Estado')).toBeVisible()
  expect(screen.queryByRole('search', { name: 'Filtros del catálogo' })).not.toBeInTheDocument()
  expect(screen.queryByRole('switch')).not.toBeInTheDocument()
  expect(screen.queryByRole('radiogroup', { name: 'Destino rápido' })).not.toBeInTheDocument()
})
