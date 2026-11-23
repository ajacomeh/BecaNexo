import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { offersApi } from './api/client'
import Offers from './pages/Offers'
import OfferEditor from './pages/OfferEditor'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [{ id: 3, nombre: 'Mérito académico' }],
  tipos_requisito: [], niveles: [], modalidades: [] }
const BASES = 'https://siau.senescyt.gob.ec/wp-content/uploads/2026/07/2026-0346.zip'
const AYUDA = 'La ficha de SIAU no publica beneficios; consúltalos en las bases oficiales (archivo ZIP) y complétalos aquí antes de publicar.'
const card = (extra) => ({ id: 7, estado: 'borrador', revision: 'pendiente', titulo: 'Convocatoria sintética', institucion: { nombre: 'Entidad ficticia' },
  beneficios: [], opciones: [], cierre: null, tipo_beca_nombre: null, ...extra })

function renderList(results) {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : { count: results.length, page: 1, page_size: 12, results })
  render(<MemoryRouter><Offers admin /></MemoryRouter>)
}

function renderEditor(offer) {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
    : path === `gestion/convocatorias/${offer.id}` ? offer : path.endsWith('/origen') ? { aplicacion: null } : { count: 0, results: [] })
  render(<MemoryRouter initialEntries={[`/gestion/convocatorias/${offer.id}`]}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
}
const draft = (extra) => ({ id: 41, titulo: 'Beca del rastreo', institucion: null, revision: 'pendiente', estado: 'borrador', activa: true, version: 2,
  origen_automatico: { publicacion_id: 17, version_id: 47 }, descartado: false, aviso_oferente: null, oferente_externo: null, tipo_beca: null,
  opciones: [], beneficios: [], requisitos: [], url_bases: BASES, ...extra })

it('tarjeta de administración: borrador del rastreo sin beneficios ni tipo se lee como dato no publicado, no como fallo', async () => {
  renderList([card({ id: 1, titulo: 'Borrador del rastreo', origen_automatico: { publicacion_id: 17 } }), card({ id: 2, titulo: 'Convocatoria manual' })])
  const rastreo = (await screen.findByRole('heading', { name: 'Borrador del rastreo' })).closest('article')
  expect(within(rastreo).getByText('Beneficios: no publicados en la ficha')).toBeVisible()
  expect(within(rastreo).getByText('Tipo: por definir')).toBeVisible()
  expect(within(rastreo).queryByText('Beneficios no especificados')).not.toBeInTheDocument()
  const manual = screen.getByRole('heading', { name: 'Convocatoria manual' }).closest('article')
  expect(within(manual).getByText('Beneficios no especificados')).toBeVisible()
  expect(within(manual).getByText('Tipo: No especificado')).toBeVisible()
})

it('tarjeta del rastreo con tipo y beneficios muestra sus datos', async () => {
  renderList([card({ origen_automatico: { publicacion_id: 17 }, tipo_beca_nombre: 'Mérito académico', beneficios: [{ concepto: 'Matrícula', porcentaje: 50 }] })])
  expect(await screen.findByText('Tipo: Mérito académico')).toBeVisible()
  expect(screen.getByText('Matrícula: 50 %')).toBeVisible()
  expect(screen.queryByText(/no publicados en la ficha/)).not.toBeInTheDocument()
})

it('editor: ayuda junto a Beneficios con enlace seguro a las bases y pista de tipo por definir', async () => {
  renderEditor(draft())
  const section = await screen.findByRole('region', { name: 'Beneficios' })
  expect(within(section).getByRole('note')).toHaveTextContent(AYUDA)
  const link = within(section).getByRole('link', { name: 'Abrir bases oficiales' })
  expect(link).toHaveAttribute('href', BASES)
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.getByText(/Tipo por definir: la ficha de SIAU no indica el tipo de beca/)).toBeVisible()
})

it('editor: sin URL de bases omite el enlace; con beneficios, en manuales o con tipo asignado no muestra las ayudas', async () => {
  renderEditor(draft({ url_bases: null }))
  const section = await screen.findByRole('region', { name: 'Beneficios' })
  expect(within(section).getByRole('note')).toHaveTextContent(AYUDA)
  expect(within(section).queryByRole('link', { name: 'Abrir bases oficiales' })).not.toBeInTheDocument()
  cleanup(); vi.restoreAllMocks()
  renderEditor(draft({ url_bases: 'javascript:alert(1)' }))
  expect(within(await screen.findByRole('region', { name: 'Beneficios' })).queryByRole('link')).not.toBeInTheDocument()
  cleanup(); vi.restoreAllMocks()
  renderEditor(draft({ beneficios: [{ id: 5, concepto: 'Matrícula', porcentaje: 50, opcion_estudio: null }], tipo_beca: 3 }))
  expect(within(await screen.findByRole('region', { name: 'Beneficios' })).queryByText(AYUDA)).not.toBeInTheDocument()
  expect(screen.queryByText(/Tipo por definir/)).not.toBeInTheDocument()
  cleanup(); vi.restoreAllMocks()
  renderEditor(draft({ origen_automatico: null }))
  expect(within(await screen.findByRole('region', { name: 'Beneficios' })).queryByText(AYUDA)).not.toBeInTheDocument()
  expect(screen.queryByText(/Tipo por definir/)).not.toBeInTheDocument()
})
