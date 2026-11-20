import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import PublicCatalog from './pages/PublicCatalog'
import Offers from './pages/Offers'

const auth = vi.hoisted(() => ({ user: null }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: auth.user, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.user = null })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], niveles: [{ valor: 'grado', nombre: 'Grado' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }], tipos_beca: [{ id: 1, nombre: 'Mérito' }], areas: [], idiomas: [], tipos_requisito: [] }
const roles = { postulante: { id: 7, nombre: 'Postulante', rol: 'postulante' }, administrador: { id: 1, nombre: 'Admin', rol: 'administrador' } }
const TABS = ['Vigentes', 'Próximas', 'Cerradas', 'Todas las publicadas']

function Location() { return <output data-testid="url">{useLocation().search}</output> }
function catalog(path = '/becas', user = null) {
  auth.user = user
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (route) => route === 'becas/catalogos' ? catalogs
    : { count: 0, page: 1, page_size: 12, results: [] })
  render(<MemoryRouter initialEntries={[path]}><PublicCatalog /><Location /></MemoryRouter>)
  return get
}

async function stateControls() {
  const tabs = within(await screen.findByRole('group', { name: 'Vigencia de las becas' })).getAllByRole('button').map(b => b.textContent)
  await userEvent.click(await screen.findByText('Más filtros'))
  const more = screen.getByText('Más filtros').closest('details')
  return { tabs, more: within(more).getAllByRole('combobox').map(select => select.labels[0].textContent), estado: screen.queryByLabelText('Estado') }
}

describe('control de estado del catálogo público', () => {
  it.each(Object.keys(roles))('tiene un único control de estado, las pestañas, para %s', async (role) => {
    catalog('/becas', roles[role])
    const controls = await stateControls()
    expect(controls.tabs).toEqual(TABS)
    expect(controls.estado).toBeNull()
    expect(controls.more).toEqual(['Tipo de beca'])
  })

  it('es idéntico para el postulante y el administrador, y no cambia la fila superior del postulante', async () => {
    catalog('/becas', roles.postulante)
    const applicant = await stateControls()
    expect(screen.getByRole('group', { name: 'Modo de resultados' })).toHaveTextContent('Todas las becasPara ti · IA')
    cleanup()
    catalog('/becas', roles.administrador)
    const admin = await stateControls()
    expect(admin).toEqual(applicant)
    expect(screen.queryByRole('group', { name: 'Modo de resultados' })).not.toBeInTheDocument()
  })

  it.each([
    ['cerrada', 'Cerradas'], ['proxima', 'Próximas'], ['todas', 'Todas las publicadas'],
    ['abierta', 'Vigentes'], ['cierre_hoy', 'Vigentes'], ['sin_fecha', 'Todas las publicadas'],
  ])('un enlace con ?estado=%s marca la pestaña %s y consulta la API con el mismo parámetro', async (estado, tab) => {
    const get = catalog(`/becas?estado=${estado}`)
    expect(await screen.findByRole('button', { name: tab, pressed: true })).toBeVisible()
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1)
    expect(get).toHaveBeenCalledWith('becas', { estado })
  })

  it('«Limpiar filtros» vuelve a Vigentes y quita el estado de la URL', async () => {
    catalog('/becas?estado=cerrada&tipo_beca=1&nivel=grado')
    const u = userEvent.setup()
    expect(await screen.findByRole('button', { name: 'Cerradas', pressed: true })).toBeVisible()
    await u.click(await screen.findByRole('button', { name: 'Limpiar filtros' }))
    expect(screen.getByTestId('url')).toBeEmptyDOMElement()
    expect(screen.getByRole('button', { name: 'Vigentes', pressed: true })).toBeVisible()
  })

  it('aplicar otros filtros conserva la pestaña elegida', async () => {
    const get = catalog('/becas?estado=proxima')
    const u = userEvent.setup()
    await u.selectOptions(await screen.findByLabelText('Nivel'), 'grado')
    await u.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(get).toHaveBeenCalledWith('becas', { estado: 'proxima', nivel: 'grado' })
    expect(screen.getByRole('button', { name: 'Próximas', pressed: true })).toBeVisible()
  })
})

describe('pantalla de Convocatorias del administrador', () => {
  it('conserva su propio filtro de estado con borrador y pausada', async () => {
    auth.user = roles.administrador
    vi.spyOn(offersApi, 'get').mockImplementation(async (route) => route === 'becas/catalogos' ? catalogs
      : { count: 0, page: 1, page_size: 12, results: [] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
    await userEvent.click(await screen.findByText('Más filtros'))
    const estado = screen.getByLabelText('Estado')
    expect(within(estado).getAllByRole('option').map(o => o.value)).toEqual(['', 'borrador', 'pausada', 'abierta', 'cerrada', 'proxima', 'sin_fecha'])
    expect(screen.queryByRole('group', { name: 'Vigencia de las becas' })).not.toBeInTheDocument()
  })
})
