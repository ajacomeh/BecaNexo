import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import PublicCatalog from './pages/PublicCatalog'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: null }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const ETIQUETA = 'Incluir becas de entidades no ecuatorianas o sin confirmar'
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], niveles: [{ valor: 'grado', nombre: 'Grado' }],
  modalidades: [{ valor: 'virtual', nombre: 'Virtual' }], tipos_beca: [{ id: 1, nombre: 'Mérito' }], areas: [] }
const ecuatoriana = { id: 1, titulo: 'Beca de entidad ecuatoriana', institucion: { nombre: 'Universidad Ecuatoriana' }, estado: 'abierta', beneficios: [], opciones: [] }
const extranjera = { id: 2, titulo: 'Beca de entidad extranjera', institucion: null, oferente_externo: { no_ecuatoriano: true, nombre: 'Universidad Extranjera' },
  estado: 'abierta', beneficios: [], opciones: [] }

function Location() { return <output data-testid="url">{useLocation().search}</output> }

function open(path = '/becas', { vacio = false } = {}) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (ruta, params = {}) => {
    if (ruta === 'becas/catalogos') return catalogs
    const results = vacio ? [] : params.incluir_no_ecuatorianas === '1' ? [ecuatoriana, extranjera] : [ecuatoriana]
    return { count: results.length, page: 1, page_size: 12, results }
  })
  render(<MemoryRouter initialEntries={[path]}><PublicCatalog /><Location /></MemoryRouter>)
  return get
}
const ultimaConsulta = (get) => get.mock.calls.filter(([ruta]) => ruta === 'becas').at(-1)[1]

it('la casilla está desmarcada por defecto y la consulta no incluye a las demás entidades', async () => {
  const get = open()
  const casilla = await screen.findByLabelText(ETIQUETA)
  expect(casilla).not.toBeChecked()
  expect(casilla).toHaveAccessibleDescription('Por defecto se muestran solo becas de entidades ecuatorianas.')
  expect(await screen.findByText('Beca de entidad ecuatoriana')).toBeVisible()
  expect(screen.queryByText('Beca de entidad extranjera')).not.toBeInTheDocument()
  expect(ultimaConsulta(get)).not.toHaveProperty('incluir_no_ecuatorianas')
  expect(screen.getByText('1 convocatoria encontrada')).toHaveAttribute('role', 'status')
})

it('marcar y aplicar incluye las demás, deja el parámetro en la URL y desmarcar lo quita', async () => {
  const get = open()
  const u = userEvent.setup()
  await u.click(await screen.findByLabelText(ETIQUETA))
  await u.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  expect(await screen.findByText('Beca de entidad extranjera')).toBeVisible()
  expect(screen.getByText('Oferente: Universidad Extranjera (no ecuatoriano)')).toBeVisible()
  expect(screen.getByText('2 convocatorias encontradas')).toBeVisible()
  expect(screen.getByTestId('url')).toHaveTextContent('incluir_no_ecuatorianas=1')
  expect(ultimaConsulta(get)).toMatchObject({ incluir_no_ecuatorianas: '1' })
  expect(screen.getByLabelText(ETIQUETA)).toBeChecked()
  await u.click(screen.getByLabelText(ETIQUETA))
  await u.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  await waitFor(() => expect(screen.queryByText('Beca de entidad extranjera')).not.toBeInTheDocument())
  expect(screen.getByTestId('url')).not.toHaveTextContent('incluir_no_ecuatorianas')
})

it('se conserva al recargar o compartir la URL y al cambiar de pestaña', async () => {
  const get = open('/becas?incluir_no_ecuatorianas=1')
  expect(await screen.findByLabelText(ETIQUETA)).toBeChecked()
  expect(await screen.findByText('Beca de entidad extranjera')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Cerradas' }))
  await waitFor(() => expect(ultimaConsulta(get)).toMatchObject({ estado: 'cerrada', incluir_no_ecuatorianas: '1' }))
})

it('«Limpiar filtros» la desmarca y quita el parámetro', async () => {
  open('/becas?incluir_no_ecuatorianas=1&q=beca')
  const u = userEvent.setup()
  expect(await screen.findByLabelText(ETIQUETA)).toBeChecked()
  await u.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
  await waitFor(() => expect(screen.getByTestId('url')).toHaveTextContent(/^$/))
  expect(await screen.findByLabelText(ETIQUETA)).not.toBeChecked()
})

it('estado vacío con la casilla desmarcada sugiere incluir las demás entidades', async () => {
  open('/becas', { vacio: true })
  expect(await screen.findByRole('heading', { name: 'No hay becas de entidades ecuatorianas con estos filtros.' })).toBeVisible()
  expect(screen.getByText('Puedes incluir becas de entidades no ecuatorianas o sin confirmar.')).toBeVisible()
  cleanup(); vi.restoreAllMocks()
  open('/becas?incluir_no_ecuatorianas=1', { vacio: true })
  expect(await screen.findByRole('heading', { name: 'No hay convocatorias disponibles actualmente' })).toBeVisible()
})

it('se conserva al paginar', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (ruta, params = {}) => ruta === 'becas/catalogos' ? catalogs
    : { count: 30, page: Number(params.page || 1), page_size: 12, results: [ecuatoriana, extranjera] })
  render(<MemoryRouter initialEntries={['/becas?incluir_no_ecuatorianas=1']}><PublicCatalog /><Location /></MemoryRouter>)
  await screen.findAllByText('Beca de entidad extranjera')
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  await waitFor(() => expect(ultimaConsulta(get)).toMatchObject({ page: '2', incluir_no_ecuatorianas: '1' }))
  expect(screen.getByTestId('url')).toHaveTextContent('incluir_no_ecuatorianas=1')
})
