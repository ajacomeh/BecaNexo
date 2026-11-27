import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { offersApi, ApiError } from './api/client'
import SimilarOffers from './components/SimilarOffers'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const results = [
  { id: 21, titulo: 'Becas de educación continua', estado: 'abierta', institucion: { id: 4, nombre: 'Instituto sintético' }, oferente_externo: null, niveles: ['no_aplica'], campo_conocimiento: 'Educación' },
  { id: 9, titulo: 'Innovación educativa', estado: 'cerrada', institucion: null, oferente_externo: null, niveles: ['maestria', 'doctorado'], campo_conocimiento: null },
]

function show(offerId = 5) {
  return render(<MemoryRouter><SimilarOffers offerId={offerId} /></MemoryRouter>)
}

describe('becas similares', () => {
  it('muestra tarjetas con estado, entidad, nivel y enlace al detalle', async () => {
    const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ results })
    show()
    expect(screen.getByRole('status')).toHaveTextContent('Buscando becas similares…')
    const list = await screen.findByRole('list', { name: 'Becas similares' })
    expect(get).toHaveBeenCalledWith('becas/5/similares')
    expect(screen.getByRole('heading', { level: 2, name: 'Becas similares' })).toBeVisible()
    expect(screen.getByText(/calculadas con un modelo de IA local\. No indican que cumplas sus requisitos\./)).toBeVisible()
    const cards = within(list).getAllByRole('listitem')
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByRole('heading', { level: 3, name: 'Becas de educación continua' })).toBeVisible()
    expect(within(cards[0]).getByText('Abierta')).toBeVisible()
    expect(within(cards[0]).getByText('Instituto sintético')).toBeVisible()
    expect(within(cards[0]).getByText('No aplica (educación continua)')).toBeVisible()
    expect(within(cards[0]).getByRole('link', { name: 'Ver detalle: Becas de educación continua' })).toHaveAttribute('href', '/becas/21')
    expect(within(cards[1]).getByText('Cerrada')).toBeVisible()
    expect(within(cards[1]).getByText('Niveles')).toBeVisible()
    expect(within(cards[1]).getByText('Maestría, Doctorado')).toBeVisible()
    expect(within(cards[1]).getByText('Entidad oferente: No identificada')).toBeVisible()
  })

  it('sin similares no muestra la sección', async () => {
    const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ results: [] })
    show()
    await vi.waitFor(() => expect(get).toHaveBeenCalled())
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Becas similares' })).not.toBeInTheDocument())
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('si la consulta falla no muestra la sección ni un error', async () => {
    vi.spyOn(offersApi, 'get').mockRejectedValue(new ApiError('Error de conexión.'))
    show()
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Becas similares' })).not.toBeInTheDocument())
    expect(screen.queryByText('Error de conexión.')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
