import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { offersApi } from './api/client'
import OfferEditor from './pages/OfferEditor'

const auth = vi.hoisted(() => ({ status: 'authenticated', user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }))
vi.mock('./auth/context', () => ({ useAuth: () => auth }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_requisito: [], modalidades: [],
  tipos_beca: [{ id: 1, nombre: 'Mérito académico' }, { id: 2, nombre: 'Investigación' }],
  niveles_opcion: [{ valor: 'grado', nombre: 'Tercer nivel / grado' }, { valor: 'maestria', nombre: 'Maestría' }] }
const draft = { id: 84, titulo: 'Becas de maestría sintéticas', institucion: null, revision: 'pendiente', estado: 'borrador', activa: true, version: 1,
  tipo_beca: null, origen_automatico: { publicacion_id: 9, version_id: 9 }, descartado: false, aviso_oferente: null, oferente_externo: null,
  opciones: [], beneficios: [], requisitos: [] }
const SUGERENCIAS = {
  nivel: { valor: 'maestria', etiqueta: 'Maestría', origen: 'deducido del texto' },
  tipo_beca: { id: 1, nombre: 'Mérito académico', origen: 'deducido del título' },
  duplicados: [{ id: 66, titulo: 'Becas de maestría sintéticas 2026-2027', estado: 'publicada', motivo: 'título casi idéntico' }],
}

function open(suggestions, offer = draft) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
    : path === `gestion/convocatorias/${offer.id}` ? offer : path.endsWith('/sugerencias') ? suggestions
      : path.endsWith('/origen') ? { aplicacion: null } : { count: 0, results: [] })
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({})
  render(<MemoryRouter initialEntries={[`/gestion/convocatorias/${offer.id}`]}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
  return { get, write }
}

it('muestra las sugerencias con su origen, la etiqueta de confirmación y los posibles duplicados', async () => {
  open(SUGERENCIAS)
  const block = (await screen.findByRole('heading', { name: 'Sugerencias automáticas' })).closest('section')
  expect(within(block).getByText(/Sugerencia automática: confírmala tú/)).toBeVisible()
  expect(within(block).getByText('Maestría')).toBeVisible()
  expect(within(block).getByText('(deducido del texto)', { exact: false })).toBeVisible()
  expect(within(block).getByText('Mérito académico')).toBeVisible()
  expect(within(block).getByText('Revisa antes de decidir.')).toBeVisible()
  const duplicates = within(block).getByRole('list', { name: 'Posibles duplicados' })
  expect(within(duplicates).getByRole('link', { name: '#66 Becas de maestría sintéticas 2026-2027' })).toHaveAttribute('href', '/gestion/convocatorias/66')
  expect(within(duplicates).getByText(/Publicada · título casi idéntico/)).toBeVisible()
  expect(block).not.toHaveTextContent('%')
})

it('«Usar sugerencia» rellena el tipo de beca y abre la opción con el nivel, sin guardar nada', async () => {
  const { write } = open(SUGERENCIAS)
  const user = userEvent.setup()
  await screen.findByRole('heading', { name: 'Sugerencias automáticas' })
  expect(screen.getByLabelText('Tipo de beca')).toHaveValue('')
  await user.click(screen.getByRole('button', { name: 'Usar sugerencia de tipo de beca: Mérito académico' }))
  expect(screen.getByLabelText('Tipo de beca')).toHaveValue('1')
  await user.click(screen.getByRole('button', { name: 'Usar sugerencia de nivel: Maestría' }))
  const options = screen.getByRole('region', { name: 'Opciones de estudio' })
  expect(within(options).getByRole('heading', { name: 'Nuevo registro' })).toBeVisible()
  expect(within(options).getByLabelText(/^Nivel/)).toHaveValue('maestria')
  expect(write).not.toHaveBeenCalled()
})

it('sin sugerencias (o si la consulta falla) el bloque no aparece', async () => {
  open({ nivel: null, tipo_beca: null, duplicados: [] })
  await screen.findByRole('heading', { name: 'Revisión y publicación' })
  expect(screen.queryByRole('heading', { name: 'Sugerencias automáticas' })).not.toBeInTheDocument()
  cleanup(); vi.restoreAllMocks()
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path.endsWith('/sugerencias')) throw new Error('fallo')
    return path === 'becas/catalogos' ? catalogs : path === 'gestion/convocatorias/84' ? draft : path.endsWith('/origen') ? { aplicacion: null } : { count: 0, results: [] }
  })
  render(<MemoryRouter initialEntries={['/gestion/convocatorias/84']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
  await screen.findByRole('heading', { name: 'Revisión y publicación' })
  expect(get).toHaveBeenCalledWith('gestion/convocatorias/84/sugerencias')
  expect(screen.queryByRole('heading', { name: 'Sugerencias automáticas' })).not.toBeInTheDocument()
})

it('no consulta sugerencias para convocatorias ya publicadas', async () => {
  const { get } = open(SUGERENCIAS, { ...draft, revision: 'validada', estado: 'abierta' })
  await screen.findByRole('heading', { name: 'Revisión y publicación' })
  expect(get.mock.calls.some(([path]) => path.endsWith('/sugerencias'))).toBe(false)
})
