import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Recommendations from './components/Recommendations'
import CatalogCard from './components/CatalogCard'
import { offersApi } from './api/client'
import { AuthContext } from './auth/context'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [], niveles: [], modalidades: [], tipos_beca: [] }
const offer = (id, titulo) => ({ id, titulo, institucion: { nombre: 'Entidad' }, estado: 'abierta', beneficios: [], opciones: [] })
const item = (id, titulo, elegibilidad) => ({ convocatoria: offer(id, titulo), elegibilidad,
  afinidad: { estado: 'calculada', explicacion: 'Se compararon áreas declaradas.' }, preferencias: { declaradas: false, coincidencias: [] } })
// Orden del servidor: primero las que cumple, luego las pendientes y al final las que no cumple.
const usuario = { user: { id: 1, rol: 'postulante' } }
const state = { data: { results: [item(1, 'Beca que cumple', 'cumple'), item(2, 'Beca pendiente', 'desconocido'), item(3, 'Beca que no cumple', 'no_cumple')] } }

function mount() {
  vi.spyOn(offersApi, 'get').mockResolvedValue({})
  render(<MemoryRouter><AuthContext.Provider value={usuario}><Recommendations catalogs={catalogs} state={state} onRefresh={vi.fn()} /></AuthContext.Provider></MemoryRouter>)
  return screen.getAllByRole('article')
}

it.each([
  [0, 'cumple', 'Requisitos declarados: coinciden', 'Requisitos obligatorios comparables coinciden según lo declarado'],
  [1, 'desconocido', 'Requisitos: información pendiente', 'Falta información para confirmar los requisitos'],
  [2, 'no_cumple', 'Requisitos: no cumple', 'Hay un incumplimiento obligatorio declarado'],
])('la tarjeta %i muestra el estado %s con color, ícono, texto y nombre accesible', (index, estado, etiqueta, explicacion) => {
  const card = within(mount()[index])
  const badge = card.getByRole('img', { name: etiqueta })
  expect(badge).toHaveClass('status-pill', 'recommendation-status', `recommendation-status-${estado}`)
  expect(badge).toHaveTextContent(etiqueta)
  expect(badge.querySelector('svg.ui-icon')).not.toBeNull()
  // Junto a la etiqueta de vigencia, que no cambia.
  expect(card.getByText('Abierta')).toHaveClass('status-pill', 'state-abierta')
  const bloque = card.getByText('Requisitos').closest('p')
  expect(bloque).toHaveClass('recommendation-requirements', `recommendation-requirements-${estado}`)
  expect(bloque.querySelector('svg.ui-icon')).not.toBeNull()
  expect(bloque).toHaveTextContent(explicacion)
})

it('deja neutros los bloques de afinidad temática y preferencias', () => {
  const card = within(mount()[2])
  for (const titulo of ['Afinidad temática', 'Preferencias']) {
    const bloque = card.getByText(titulo).closest('p')
    expect(bloque.className).toBe('')
    expect(bloque.querySelector('svg')).toBeNull()
  }
})

it('conserva el orden de las tarjetas que entrega el servidor', () => {
  const cards = mount()
  expect(cards.map(card => within(card).getByRole('heading', { level: 2 }).textContent)).toEqual(['Beca que cumple', 'Beca pendiente', 'Beca que no cumple'])
})

it('no muestra el indicador en «Todas las becas»: la misma tarjeta sin recomendación queda como antes', () => {
  render(<MemoryRouter><AuthContext.Provider value={usuario}><CatalogCard offer={offer(9, 'Beca del catálogo')} catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
  const card = screen.getByRole('article')
  expect(card.querySelector('.recommendation-status, .recommendation-requirements, .recommendation-explanation')).toBeNull()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
  expect(screen.getByText('Abierta')).toHaveClass('status-pill', 'state-abierta')
})
