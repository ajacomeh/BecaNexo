import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { offersApi, ApiError } from './api/client'
import FavoriteButton from './components/FavoriteButton'
import Favorites from './pages/Favorites'

const auth = vi.hoisted(() => ({ user: { nombre: 'Postulante', rol: 'postulante' } }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: auth.user, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.user = { nombre: 'Postulante', rol: 'postulante' } })

describe('favoritos', () => {
  it('guarda y quita solo después de respuesta correcta', async () => {
    const write = vi.spyOn(offersApi, 'write').mockResolvedValueOnce({ id: 9 }).mockResolvedValueOnce(null)
    render(<FavoriteButton offerId={3} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Guardar en favoritos' }))
    expect(write).toHaveBeenCalledWith('favoritos', 'POST', { convocatoria: 3 })
    await user.click(await screen.findByRole('button', { name: 'Quitar de favoritos' }))
    expect(write).toHaveBeenLastCalledWith('favoritos/9', 'DELETE')
    expect(screen.getByRole('button', { name: 'Guardar en favoritos' })).toBeVisible()
  })

  it('mantiene el estado guardado si falla quitar', async () => {
    vi.spyOn(offersApi, 'write').mockRejectedValue(new ApiError('Error de conexión.'))
    render(<FavoriteButton offerId={3} initialId={9} />)
    await userEvent.click(screen.getByRole('button', { name: 'Quitar de favoritos' }))
    expect(await screen.findByText('Error de conexión.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Quitar de favoritos' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('no marca como guardado si falla agregar', async () => {
    vi.spyOn(offersApi, 'write').mockRejectedValue(new ApiError('Rechazado.', 403))
    render(<FavoriteButton offerId={3} />)
    await userEvent.click(screen.getByRole('button', { name: 'Guardar en favoritos' }))
    expect(await screen.findByText('Rechazado.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Guardar en favoritos' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('no muestra controles administrativos y ofrece login a visitantes', () => {
    auth.user = { rol: 'administrador' }
    const { rerender } = render(<MemoryRouter><FavoriteButton offerId={3} /></MemoryRouter>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    auth.user = null; rerender(<MemoryRouter><FavoriteButton offerId={3} /></MemoryRouter>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Guardar en favoritos' })).toHaveAttribute('href', '/login?next=%2Fbecas%2F3')
  })

  it('restaura favoritos desde el servidor y permite quitar una oferta oculta', async () => {
    const row = { id: 9, disponible: false, convocatoria: null, aviso: 'Esta oportunidad ya no está disponible.' }
    let requests = 0
    vi.spyOn(offersApi, 'get').mockImplementation((path) => {
      if (path === 'notificaciones') return Promise.resolve({ no_leidas: 0 })
      requests += 1
      return Promise.resolve(requests === 1 ? { count: 1, page_size: 12, results: [row] } : { count: 0, page_size: 12, results: [] })
    })
    vi.spyOn(offersApi, 'write').mockResolvedValue(null)
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    expect(await screen.findByText(row.aviso)).toBeVisible()
    expect(screen.queryByRole('link', { name: 'Ver convocatoria' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Quitar de favoritos' }))
    expect(await screen.findByText('Aún no tienes favoritos')).toBeVisible()
  })

  it.each([0, 1, 8, 12])('oculta paginación con %i favoritos, incluidos los no disponibles', async count => {
    const rows = Array.from({ length: count }, (_, index) => ({ id: index + 1, disponible: false,
      convocatoria: null, aviso: 'Esta oportunidad ya no está disponible.' }))
    vi.spyOn(offersApi, 'get').mockResolvedValue({ count, page: 1, page_size: 12, results: rows })
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    if (count) expect(await screen.findAllByText('Esta oportunidad ya no está disponible.')).toHaveLength(count)
    else expect(await screen.findByText('Aún no tienes favoritos')).toBeVisible()
    expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument()
  })

  it('navega varias páginas y respeta los límites sin excluir favoritos no disponibles', async () => {
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async (_, { page }) => ({ count: 25, page, page_size: 12,
      results: Array.from({ length: page === 3 ? 1 : 12 }, (_, index) => ({ id: (page - 1) * 12 + index + 1,
        disponible: false, convocatoria: null, aviso: 'Esta oportunidad ya no está disponible.' })) }))
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    const user = userEvent.setup()
    let nav = await screen.findByRole('navigation', { name: 'Paginación' })
    expect(within(nav).getByText('Página 1 de 3')).toBeVisible()
    expect(within(nav).getByRole('button', { name: 'Anterior' })).toBeDisabled()
    await user.click(within(nav).getByRole('button', { name: 'Siguiente' }))
    nav = await screen.findByRole('navigation', { name: 'Paginación' })
    expect(await within(nav).findByText('Página 2 de 3')).toBeVisible()
    expect(within(nav).getByRole('button', { name: 'Anterior' })).toBeEnabled()
    await user.click(within(nav).getByRole('button', { name: 'Siguiente' }))
    expect(await screen.findByText('Página 3 de 3')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Anterior' }))
    expect(await screen.findByText('Página 2 de 3')).toBeVisible()
    expect(get).toHaveBeenCalledWith('favoritos', { page: 3 })
  })

  it('regresa a la última página válida cuando el total disminuye', async () => {
    let removed = false
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async (_, { page }) => ({ count: removed ? 12 : 13,
      page, page_size: 12, results: page === 1 ? Array.from({ length: 12 }, (_, index) => ({ id: index + 1,
        disponible: false, convocatoria: null, aviso: 'Esta oportunidad ya no está disponible.' }))
        : removed ? [] : [{ id: 13, disponible: false, convocatoria: null, aviso: 'Esta oportunidad ya no está disponible.' }] }))
    const write = vi.spyOn(offersApi, 'write').mockImplementation(async () => { removed = true })
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    await userEvent.click(within(await screen.findByRole('navigation', { name: 'Paginación' })).getByRole('button', { name: 'Siguiente' }))
    expect(await screen.findByText('Página 2 de 2')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Quitar de favoritos' }))
    expect(await screen.findAllByText('Esta oportunidad ya no está disponible.')).toHaveLength(12)
    expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('favoritos', { page: 2 })
    expect(get).toHaveBeenCalledWith('favoritos', { page: 1 })
    expect(write).toHaveBeenCalledTimes(1)
  })

  it('no inventa el cierre de una oferta guardada cuando el resumen no incluye la fecha', async () => {
    const row = { id: 10, disponible: true, convocatoria: { id: 3, titulo: 'Oferta de prueba', institucion: 'Entidad', estado: 'cierre_hoy', cierre: null } }
    vi.spyOn(offersApi, 'get').mockResolvedValue({ count: 1, page_size: 12, results: [row] })
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    expect(await screen.findByText('Oferta de prueba')).toBeVisible()
    expect(screen.getByText('Cierre').nextElementSibling).toHaveTextContent('Consulta el detalle para confirmar el cierre')
    expect(screen.getByRole('link', { name: 'Ver convocatoria' })).toHaveAttribute('href', '/becas/3')
  })

  it('presenta carga, error y reintento del listado', async () => {
    let requests = 0
    vi.spyOn(offersApi, 'get').mockImplementation((path) => {
      if (path === 'notificaciones') return Promise.resolve({ no_leidas: 0 })
      requests += 1
      return requests === 1 ? Promise.reject(new ApiError('No hay conexión.')) : Promise.resolve({ count: 0, results: [] })
    })
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando favoritos')
    expect(await screen.findByText('No hay conexión.')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('Aún no tienes favoritos')).toBeVisible()
  })

  it('evita doble envío mientras espera al servidor', async () => {
    let finish
    const write = vi.spyOn(offersApi, 'write').mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    render(<FavoriteButton offerId={3} />)
    await userEvent.dblClick(screen.getByRole('button', { name: 'Guardar en favoritos' }))
    expect(write).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button')).toBeDisabled()
    finish({ id: 9 })
    expect(await screen.findByRole('button', { name: 'Quitar de favoritos' })).toBeVisible()
  })
})
