import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { offersApi } from './api/client'
import App from './App'
import Offers from './pages/Offers'
import OfferEditor from './pages/OfferEditor'

const auth = vi.hoisted(() => ({ status: 'authenticated', user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }))
vi.mock('./auth/context', () => ({ useAuth: () => auth }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const AVISO = 'La ficha oficial ya no está disponible en SIAU'
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }
const pub = (id, extra) => ({ id, titulo: `Publicación ${id}`, fuente: { id: 1, nombre: 'SIAU' }, url_original: `https://siau.senescyt.gob.ec/p${id}/`,
  primera_deteccion: '2026-11-01T10:00:00Z', ultima_deteccion: '2026-11-23T10:00:00Z', version_observada_id: 1, convocatoria_id: null,
  situacion: { tipo: 'borrador', convocatoria_id: 60 + id, pendientes: 0, descartado: false }, retirada_en: null, ...extra })

it('Publicaciones detectadas: etiqueta «Retirada de SIAU» solo en las marcadas', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'gestion/rastreo/publicaciones'
    ? { count: 2, page: 1, page_size: 12, results: [pub(17, { retirada_en: '2026-11-25T01:00:00Z' }), pub(19)] } : { count: 0, page: 1, page_size: 12, results: [] })
  render(<MemoryRouter initialEntries={['/gestion/rastreo']}><App /></MemoryRouter>)
  const retirada = (await screen.findByRole('link', { name: 'Publicación 17' })).closest('article')
  expect(within(retirada).getByText('Retirada de SIAU')).toHaveClass('situation-retirada')
  const vigente = screen.getByRole('link', { name: 'Publicación 19' }).closest('article')
  expect(within(vigente).queryByText('Retirada de SIAU')).not.toBeInTheDocument()
})

it('el nuevo código se muestra como «Ficha retirada de SIAU» en Incidencias', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path, params = {}) => {
    if (path === 'gestion/rastreo/ejecuciones/18') return { id: 18, fuente: { nombre: 'SIAU' }, estado: 'finalizada', accesos: 12, documentos_distintos: 10,
      publicaciones_observadas: 12, versiones_nuevas: 0, observaciones_sin_cambios: 10, incidencias_error: 0, incidencias_aviso: 2 }
    if (path === 'gestion/rastreo/ejecuciones/18/incidencias') return { count: 2, page: 1, page_size: params.page_size, results: [],
      resumen: [{ codigo: 'FICHA_NO_DISPONIBLE', gravedad: 'aviso', total: 2 }] }
    return { count: 0, page: 1, page_size: 25, results: [] }
  })
  render(<MemoryRouter initialEntries={['/gestion/rastreo/ejecuciones/18']}><App /></MemoryRouter>)
  const tab = (await screen.findAllByRole('tab', {}, { timeout: 3000 })).find((t) => t.textContent.startsWith('Incidencias'))
  await userEvent.click(tab)
  const groups = await screen.findByRole('list', { name: 'Incidencias agrupadas por tipo' })
  expect(within(groups).getByRole('button')).toHaveTextContent('AvisoFicha retirada de SIAU×2')
})

it('tarjeta de Convocatorias: aviso discreto solo si la ficha vinculada fue retirada', async () => {
  const offer = (id, extra) => ({ id, titulo: `Convocatoria ${id}`, estado: 'cerrada', revision: 'validada', institucion: { nombre: 'Entidad' },
    beneficios: [], opciones: [], areas: [], origen_automatico: { publicacion_id: id }, ...extra })
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
    : { count: 2, page: 1, page_size: 12, results: [offer(62, { ficha_retirada: true }), offer(63, { ficha_retirada: false })] })
  render(<MemoryRouter><Offers admin /></MemoryRouter>)
  const retirada = (await screen.findByRole('heading', { name: 'Convocatoria 62' })).closest('article')
  expect(within(retirada).getByText(AVISO)).toHaveClass('small-note')
  expect(within(retirada).getByText('Cerrada')).toBeVisible() // el estado no cambia
  expect(within(screen.getByRole('heading', { name: 'Convocatoria 63' }).closest('article')).queryByText(AVISO)).not.toBeInTheDocument()
})

it('editor: aviso discreto en convocatorias vinculadas a una ficha retirada', async () => {
  const data = (extra) => ({ id: 62, titulo: 'Convocatoria 62', institucion: { id: 1, nombre: 'Entidad' }, revision: 'validada', estado: 'cerrada', activa: true, version: 3,
    origen_automatico: { publicacion_id: 18, version_id: 48 }, descartado: false, aviso_oferente: null, oferente_externo: null,
    opciones: [], beneficios: [], requisitos: [], ...extra })
  const open = (offer) => {
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
      : path === 'gestion/convocatorias/62' ? offer : path.endsWith('/origen') ? { aplicacion: null } : { count: 0, results: [] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias/62']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
  }
  open(data({ ficha_retirada: true }))
  expect(await screen.findByText(AVISO)).toHaveAttribute('role', 'note')
  cleanup(); vi.restoreAllMocks()
  open(data({ ficha_retirada: false }))
  await screen.findByRole('heading', { name: 'Revisión y publicación' })
  expect(screen.queryByText(AVISO)).not.toBeInTheDocument()
})
