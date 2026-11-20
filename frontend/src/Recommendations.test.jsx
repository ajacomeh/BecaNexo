import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import PublicCatalog from './pages/PublicCatalog'
import { offersApi } from './api/client'
import { AuthContext } from './auth/context'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [], niveles: [], modalidades: [], tipos_beca: [] }
const offer = (id, titulo) => ({ id, titulo, institucion: { nombre: 'Entidad' }, estado: 'sin_fecha', beneficios: [], opciones: [] })
const catalog = { count: 1, page: 2, page_size: 12, results: [offer(7, 'Beca del catálogo')] }
const recommended = { aviso: 'Comparación orientativa', results: [
  { convocatoria: offer(8, 'Beca recomendada'), elegibilidad: 'no_cumple', afinidad: { estado: 'calculada', explicacion: 'Se compararon áreas declaradas.' }, preferencias: { declaradas: true, coincidencias: ['nivel de estudio'] } },
] }
const account = { id: 1, rol: 'postulante' }

function Location() { return <output data-testid="url">{useLocation().search}</output> }
function mount(get, user = account) {
  vi.spyOn(offersApi, 'get').mockImplementation(get)
  return render(<MemoryRouter initialEntries={['/becas?page=2&q=ingenieria']}>
    <AuthContext.Provider value={{ user }}><PublicCatalog /><Location /></AuthContext.Provider>
  </MemoryRouter>)
}
const responses = async path => path === 'becas/catalogos' ? catalogs : path === 'becas/recomendaciones' ? recommended : catalog

it('sustituye el catálogo por recomendaciones sin duplicar tarjetas y conserva filtros al volver', async () => {
  const get = vi.fn(responses)
  mount(get)
  const user = userEvent.setup()
  expect(await screen.findByText('Beca del catálogo')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Todas las becas' })).toHaveAttribute('aria-pressed', 'true')
  await user.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  expect(await screen.findByText('Beca recomendada')).toBeVisible()
  expect(screen.queryByText('Beca del catálogo')).not.toBeInTheDocument()
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.queryByLabelText('Buscar título, institución, área, descripción o programa')).not.toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument()
  expect(screen.getByText('Becas ordenadas según tus requisitos y afinidad académica.')).toBeVisible()
  expect(screen.getByText('La afinidad temática no garantiza elegibilidad ni adjudicación.')).toBeVisible()
  expect(screen.queryByText(/Los filtros, el orden y la paginación/)).not.toBeInTheDocument()
  expect(screen.queryByText('Comparación orientativa')).not.toBeInTheDocument()
  expect(screen.getByText(/Hay un incumplimiento obligatorio declarado/)).toBeVisible()
  expect(screen.getByText(/Calculada con el modelo local/)).toBeVisible()
  const recommendationCard = screen.getByRole('article')
  expect(recommendationCard).toHaveTextContent('Requisitos: no cumple')
  expect(recommendationCard).toHaveTextContent('Coinciden nivel de estudio.')
  expect(recommendationCard.querySelector('.recommendation-explanation')).toHaveTextContent('Se compararon áreas declaradas.')
  expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/becas/8')
  expect(screen.getByTestId('url').textContent).toContain('page=2')
  await user.click(screen.getByRole('button', { name: 'Todas las becas' }))
  expect(await screen.findByText('Beca del catálogo')).toBeVisible()
  expect(screen.queryByText('Beca recomendada')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Buscar título, institución, área, descripción o programa')).toHaveValue('ingenieria')
  await user.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  expect(await screen.findByText('Beca recomendada')).toBeVisible()
  expect(get.mock.calls.filter(([path]) => path === 'becas/recomendaciones')).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Actualizar recomendaciones' }))
  await waitFor(() => expect(get.mock.calls.filter(([path]) => path === 'becas/recomendaciones')).toHaveLength(2))
})

it('muestra carga, error y reintento sin inventar resultados, y después estado vacío', async () => {
  let resolve
  const get = vi.fn(path => path === 'becas/catalogos' ? Promise.resolve(catalogs) : path === 'becas/recomendaciones'
    ? new Promise(done => { resolve = done }) : Promise.resolve(catalog))
  mount(get)
  const user = userEvent.setup()
  await screen.findByText('Beca del catálogo')
  await user.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  expect(screen.getByText('Calculando afinidad y cargando oportunidades…')).toBeVisible()
  await act(async () => resolve(Promise.reject(new Error('Sin conexión'))))
  expect(await screen.findByText('Sin conexión')).toBeVisible()
  expect(screen.queryByText('Beca del catálogo')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Reintentar recomendaciones' }))
  await act(async () => resolve({ aviso: 'Orientativo', results: [] }))
  expect(await screen.findByText('No hay convocatorias públicas para recomendar.')).toBeVisible()
  expect(get.mock.calls.filter(([path]) => path === 'becas/recomendaciones')).toHaveLength(2)
})

it('respeta el orden recibido y distingue afinidad pendiente de elegibilidad desconocida', async () => {
  const rows = [
    { convocatoria: offer(20, 'Primera recomendación'), elegibilidad: 'desconocido', afinidad: { estado: 'modelo_no_disponible', explicacion: 'Se conserva el orden por requisitos.' }, preferencias: { declaradas: false, coincidencias: [] } },
    { convocatoria: offer(10, 'Segunda recomendación'), elegibilidad: 'no_cumple', afinidad: { estado: 'calculada', explicacion: 'Se compararon áreas.' }, preferencias: { declaradas: false, coincidencias: [] } },
  ]
  mount(path => path === 'becas/catalogos' ? Promise.resolve(catalogs) : path === 'becas/recomendaciones'
    ? Promise.resolve({ aviso: 'Resultado orientativo', results: rows }) : Promise.resolve(catalog))
  await screen.findByText('Beca del catálogo')
  await userEvent.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  await screen.findByText('Primera recomendación')
  expect(screen.getAllByRole('article').map(row => row.querySelector('h2').textContent)).toEqual(['Primera recomendación', 'Segunda recomendación'])
  expect(screen.getAllByRole('article')[0]).toHaveTextContent('Requisitos: información pendiente')
  expect(screen.getAllByRole('article')[1]).toHaveTextContent('Requisitos: no cumple')
  expect(screen.getAllByRole('article')[0].querySelector('.recommendation-explanation')).toHaveTextContent('Se conserva el orden por requisitos.')
  expect(screen.getAllByRole('article')[1].querySelector('.recommendation-explanation')).toHaveTextContent('Se compararon áreas.')
  expect(screen.getByText(/Falta información para confirmar los requisitos/)).toBeVisible()
  expect(screen.getByText(/Hay un incumplimiento obligatorio declarado/)).toBeVisible()
  expect(screen.getByText(/Pendiente. Se conserva el orden por requisitos/)).toBeVisible()
})

it('muestra coincidencia declarada sin confundirla con afinidad y conserva el orden de la API', async () => {
  const rows = [
    { convocatoria: offer(2, 'Beca compatible'), elegibilidad: 'cumple', afinidad: { estado: 'calculada', explicacion: 'Afinidad con ingeniería.' }, preferencias: { declaradas: true, coincidencias: ['destino'] } },
    { convocatoria: offer(1, 'Beca pendiente'), elegibilidad: 'desconocido', afinidad: { estado: 'calculada', explicacion: 'Afinidad con educación.' }, preferencias: { declaradas: false, coincidencias: [] } },
  ]
  mount(path => path === 'becas/catalogos' ? Promise.resolve(catalogs) : path === 'becas/recomendaciones'
    ? Promise.resolve({ results: rows }) : Promise.resolve(catalog))
  await screen.findByText('Beca del catálogo')
  await userEvent.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  await screen.findByText('Beca compatible')
  const cards = screen.getAllByRole('article')
  expect(cards.map(card => card.querySelector('h2').textContent)).toEqual(['Beca compatible', 'Beca pendiente'])
  expect(cards[0]).toHaveTextContent('Requisitos declarados: coinciden')
  expect(cards[0]).toHaveTextContent('Afinidad con ingeniería.')
  expect(cards[1]).toHaveTextContent('Requisitos: información pendiente')
  expect(cards[1]).toHaveTextContent('Afinidad con educación.')
})

it('mantiene el catálogo público sin selector de IA para administradores', async () => {
  const get = vi.fn(responses)
  mount(get, { id: 3, rol: 'administrador' })
  expect(await screen.findByText('Beca del catálogo')).toBeVisible()
  expect(screen.queryByRole('group', { name: 'Modo de resultados' })).not.toBeInTheDocument()
  expect(get.mock.calls.some(([path]) => path === 'becas/recomendaciones')).toBe(false)
})

it('permite ver recomendaciones aunque falle el listado general', async () => {
  const get = vi.fn(path => path === 'becas' ? Promise.reject(new Error('Falló el catálogo general'))
    : Promise.resolve(path === 'becas/catalogos' ? catalogs : recommended))
  mount(get)
  expect(await screen.findByText('Falló el catálogo general')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  expect(await screen.findByText('Beca recomendada')).toBeVisible()
  expect(screen.queryByText('Falló el catálogo general')).not.toBeInTheDocument()
})

it('reintenta los metadatos necesarios para representar las tarjetas', async () => {
  let attempts = 0
  mount(path => {
    if (path === 'becas/catalogos') return ++attempts === 1 ? Promise.reject(new Error('Fallaron los datos del catálogo')) : Promise.resolve(catalogs)
    return Promise.resolve(path === 'becas/recomendaciones' ? recommended : catalog)
  })
  expect(await screen.findByText('Fallaron los datos del catálogo')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  expect(screen.queryByText('Beca recomendada')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar catálogo' }))
  expect(await screen.findByText('Beca recomendada')).toBeVisible()
  expect(attempts).toBe(2)
})

it('conserva favoritos en el listado activo y descarta recomendaciones al cambiar de cuenta', async () => {
  const get = vi.fn(responses)
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ id: 15 })
  const { rerender } = mount(get)
  const user = userEvent.setup()
  await screen.findByText('Beca del catálogo')
  await user.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  await screen.findByText('Beca recomendada')
  await user.click(screen.getByRole('button', { name: 'Guardar en favoritos' }))
  expect(write).toHaveBeenCalledWith('favoritos', 'POST', { convocatoria: 8 })
  expect(await screen.findByRole('button', { name: 'Quitar de favoritos' })).toBeVisible()
  const wrap = nextUser => <MemoryRouter initialEntries={['/becas?page=2&q=ingenieria']}>
    <AuthContext.Provider value={{ user: nextUser }}><PublicCatalog /><Location /></AuthContext.Provider>
  </MemoryRouter>
  rerender(wrap(null))
  expect(screen.queryByText('Beca recomendada')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Para ti · IA' })).not.toBeInTheDocument()
  rerender(wrap({ id: 2, rol: 'postulante' }))
  await user.click(screen.getByRole('button', { name: 'Para ti · IA' }))
  await screen.findByText('Beca recomendada')
  expect(get.mock.calls.filter(([path]) => path === 'becas/recomendaciones')).toHaveLength(2)
})
