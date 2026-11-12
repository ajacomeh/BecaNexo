import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import { offersApi } from './api/client'

vi.mock('./auth/context', () => ({ useAuth: () => ({ status: 'authenticated', user: { nombre: 'Administración', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const row = (id, sector = 'publico') => ({ id, nombre: `Entidad ${id}`, sector })
const list = (results, count = results.length, page = 1) => ({ results, count, page, page_size: 2 })
const catalogs = { paises: [{ id: 1, nombre: 'Ecuador', codigo: 'EC' }] }
function open(get) {
  vi.spyOn(offersApi, 'get').mockImplementation((path, params) => path === 'becas/catalogos' ? Promise.resolve(catalogs) : Promise.resolve(get(params)))
  render(<MemoryRouter initialEntries={['/gestion/instituciones']}><App /></MemoryRouter>)
}

it('muestra estados vacíos y oculta paginación con cero o una página', async () => {
  open(() => list([]))
  expect(await screen.findByText('No hay entidades oferentes registradas.')).toBeVisible()
  expect(screen.getByText('0 entidades')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
  cleanup()
  vi.restoreAllMocks()
  open(() => list([row(1)]))
  expect(await screen.findByText('Entidad 1')).toBeVisible()
  expect(screen.getByText('1 entidad')).toBeVisible()
  expect(screen.getByText('Pública')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})

it('navega entre páginas reales y conserva la búsqueda al avanzar', async () => {
  const get = params => params.q ? list([row(params.page === 1 ? 2 : 3, 'privado')], 3, params.page) : list([row(1)], 1)
  open(get)
  await screen.findByText('Entidad 1')
  await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar entidad' }), 'beca')
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
  expect(await screen.findByText('Entidad 2')).toBeVisible()
  expect(screen.getByText('Privada')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(await screen.findByText('Entidad 3')).toBeVisible()
  expect(screen.getByText('Página 2 de 2')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Limpiar' }))
  expect(await screen.findByText('Entidad 1')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})

it('conserva las acciones de añadir y editar', async () => {
  open(() => list([row(1)]))
  await screen.findByText('Entidad 1')
  await userEvent.click(screen.getByRole('button', { name: 'Editar' }))
  expect(screen.getByRole('heading', { name: 'Editar oferente' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  await userEvent.click(screen.getByRole('button', { name: 'Añadir entidad oferente' }))
  expect(screen.getByRole('heading', { name: 'Nueva entidad oferente' })).toBeVisible()
})

it('distingue una búsqueda sin coincidencias', async () => {
  open(params => params.q ? list([]) : list([row(1)]))
  await screen.findByText('Entidad 1')
  await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar entidad' }), 'otra')
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
  expect(await screen.findByText('No encontramos entidades que coincidan con la búsqueda.')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})
