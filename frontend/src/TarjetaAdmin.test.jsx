import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import Offers from './pages/Offers'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { id: 1, nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }
const base = { institucion: { nombre: 'Entidad sintética' }, beneficios: [], cierre: null, areas: [] }
const rastreo = { ...base, id: 7, titulo: 'Borrador del rastreo', estado: 'borrador', revision: 'pendiente', institucion: null,
  origen_automatico: { publicacion_id: 17 }, ficha_retirada: true, tipo_beca_nombre: null, diagnostico: { faltan: 2 },
  opciones: [{ nivel: 'maestria', modalidad: 'virtual', activa: true }] }
const publicada = { ...base, id: 8, titulo: 'Beca publicada', estado: 'abierta', revision: 'validada', tipo_beca_nombre: 'Mérito académico',
  cierre_dia: '2027-06-30', beneficios: [{ concepto: 'Matrícula', porcentaje: '100.00' }, { concepto: 'Manutención', porcentaje: null }],
  opciones: [{ nivel: 'grado', modalidad: 'presencial', activa: true }, { nivel: 'grado', modalidad: 'virtual', activa: true }] }

async function cards() {
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? catalogs : { count: 2, page: 1, page_size: 12, results: [rastreo, publicada] })
  render(<MemoryRouter><Offers admin /></MemoryRouter>)
  const card = async title => (await screen.findByRole('heading', { name: title })).closest('article')
  return [await card('Borrador del rastreo'), await card('Beca publicada')]
}

it('usa los bloques del catálogo: icono decorativo, etiqueta arriba y valor debajo, con el cierre primero', async () => {
  const [, card] = await cards()
  const facts = card.querySelector('dl.offer-card-facts.card-facts')
  const terms = within(facts).getAllByRole('term')
  expect(terms.map(t => t.textContent)).toEqual(['Cierre', 'Opciones de estudio', 'Nivel', 'Modalidades', 'Tipo'])
  for (const term of terms) {
    expect(term.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(term.nextElementSibling.tagName).toBe('DD')
  }
  expect(terms[0].nextElementSibling).toHaveTextContent('30 jun 2027 · hora no informada')
  expect(terms.map(t => t.nextElementSibling.textContent).slice(1)).toEqual(['2', 'Grado', 'Presencial, Virtual', 'Mérito académico'])
  const financing = card.querySelector('.offer-card-financing')
  expect(within(financing).getByRole('heading', { name: 'Financiamiento', level: 3 })).toBeVisible()
  expect(within(financing).getByText('Matrícula: 100.00 % · Manutención: porcentaje no especificado')).toBeVisible()
})

it('no ocupa una celda con «Tipo» vacío y conserva el aviso, el origen del rastreo, la ficha retirada y «Editar y revisar»', async () => {
  const [card] = await cards()
  expect(within(card).queryByText('Tipo', { selector: 'dt' })).not.toBeInTheDocument()
  expect(within(card).queryByText(/por definir|No especificado$/)).not.toBeInTheDocument()
  expect(within(card).getByText('Faltan 2 pasos para publicar')).toHaveClass('card-readiness-pending')
  expect(within(card).getByText('Borrador del rastreo · Publicación 17')).toBeVisible()
  expect(within(card).getByText('La ficha oficial ya no está disponible en SIAU')).toBeVisible()
  expect(within(card).getByText('Oferente pendiente de confirmar')).toBeVisible()
  expect(within(card).getByText('Beneficios: no publicados en la ficha')).toBeVisible()
  const foot = card.querySelector('.card-foot')
  expect(foot).toBe(card.lastElementChild)
  expect(within(foot).getByRole('link', { name: 'Editar y revisar' })).toHaveAttribute('href', '/gestion/convocatorias/7')
  // Orden de lectura: cabecera, aviso de pasos, datos, beneficios y pie.
  const order = ['.card-head', '.card-readiness', 'dl.card-facts', '.offer-card-financing', '.card-foot'].map(s => [...card.children].indexOf(card.querySelector(s)))
  expect(order).toEqual([...order].sort((a, b) => a - b))
})
