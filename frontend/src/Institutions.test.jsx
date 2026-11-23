import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import { offersApi } from './api/client'

vi.mock('./auth/context', () => ({ useAuth: () => ({ status: 'authenticated', user: { nombre: 'Administración', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const row = (id, sector = 'publico', nombre = `Entidad ${String(id).padStart(2, '0')}`) => ({ id, nombre, sector, pais: 1, url_oficial: null })
const catalogs = { paises: [{ id: 1, nombre: 'Ecuador', codigo: 'EC' }] }
// Simula la API paginada (máximo 50 por página) con búsqueda por nombre en el servidor.
function open(all) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path, params = {}) => {
    if (path === 'becas/catalogos') return catalogs
    const rows = (typeof all === 'function' ? all() : all).filter(r => !params.q || r.nombre.toLowerCase().includes(params.q.toLowerCase()))
    const first = (params.page - 1) * params.page_size
    return { count: rows.length, page: params.page, page_size: params.page_size, results: rows.slice(first, first + params.page_size) }
  })
  render(<MemoryRouter initialEntries={['/gestion/instituciones']}><App /></MemoryRouter>)
  return get
}
const list = () => screen.findByRole('list').catch(() => null)

it('encabezado de administración, contador y estado vacío', async () => {
  open([])
  expect(await screen.findByText('No hay entidades oferentes registradas.')).toBeVisible()
  expect(screen.getByText('ADMINISTRACIÓN')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Entidades oferentes', level: 1 })).toBeVisible()
  expect(screen.getByText('Solo entidades ecuatorianas. El país de estudio se define por separado en cada opción.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Añadir entidad oferente' }).closest('.page-heading')).not.toBeNull()
  expect(screen.getByText('0 entidades')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})

it('filas con inicial, chip de sector y etiqueta de demostración sin repetir el prefijo', async () => {
  open([row(1, 'publico', 'DEMOSTRACIÓN · Universidad Pública de Prueba'), row(2, 'privado', 'Fundación Privada')])
  const items = within(await list()).getAllByRole('listitem')
  expect(screen.getByText('2 entidades')).toBeVisible()
  expect(within(items[0]).getByText('Universidad Pública de Prueba')).toBeVisible()
  expect(within(items[0]).queryByText(/DEMOSTRACIÓN ·/)).not.toBeInTheDocument()
  expect(within(items[0]).getByText('Demostración')).toBeVisible()
  expect(within(items[0]).getByText('U')).toHaveClass('institution-initial')
  expect(within(items[0]).getByText('Pública')).toHaveClass('institution-sector-publico')
  expect(within(items[1]).getByText('Privada')).toHaveClass('institution-sector-privado')
  expect(within(items[1]).queryByText('Demostración')).not.toBeInTheDocument()
  expect(within(items[1]).getByRole('button', { name: 'Editar Fundación Privada' })).toBeVisible()
})

it('busca en el servidor, filtra por sector y limpia los filtros', async () => {
  const get = open([row(1, 'publico', 'Instituto Público'), row(2, 'privado', 'Instituto Privado'), row(3, 'privado', 'Fundación Becas')])
  await screen.findByText('3 entidades')
  await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar entidad' }), 'instituto')
  await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
  expect(await screen.findByText('2 entidades')).toBeVisible()
  expect(get).toHaveBeenCalledWith('gestion/instituciones', { page: 1, page_size: 50, q: 'instituto' })
  await userEvent.selectOptions(screen.getByLabelText('Sector'), 'privado')
  expect(screen.getByText('2 entidades')).toBeVisible() // el filtro se aplica al pulsar «Aplicar»
  await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
  expect(await screen.findByText('1 entidad')).toBeVisible()
  expect(screen.getByText('Instituto Privado')).toBeVisible()
  expect(screen.queryByText('Instituto Público')).not.toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Sector'), 'publico')
  await userEvent.clear(screen.getByRole('searchbox', { name: 'Buscar entidad' }))
  await userEvent.type(screen.getByRole('searchbox', { name: 'Buscar entidad' }), 'fundación')
  await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }))
  expect(await screen.findByText('No hay entidades con esos filtros.')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
  expect(await screen.findByText('3 entidades')).toBeVisible()
  expect(screen.getByLabelText('Sector')).toHaveValue('')
  expect(screen.getByRole('searchbox', { name: 'Buscar entidad' })).toHaveValue('')
})

it('paginador de 25 solo con más de una página y texto «1–25 de N»', async () => {
  open(Array.from({ length: 60 }, (_, i) => row(i + 1)))
  await screen.findByText('60 entidades')
  expect(within(await list()).getAllByRole('listitem')).toHaveLength(25)
  const pager = screen.getByRole('navigation', { name: 'Paginación de oferentes' })
  expect(within(pager).getByText('1–25 de 60')).toBeVisible()
  expect(within(pager).getByRole('button', { name: 'Anterior' })).toBeDisabled()
  await userEvent.click(within(pager).getByRole('button', { name: 'Siguiente' }))
  expect(within(pager).getByText('26–50 de 60')).toBeVisible()
  await userEvent.click(within(pager).getByRole('button', { name: 'Siguiente' }))
  expect(within(pager).getByText('51–60 de 60')).toBeVisible()
  expect(within(pager).getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  cleanup(); vi.restoreAllMocks()
  open(Array.from({ length: 25 }, (_, i) => row(i + 1)))
  await screen.findByText('25 entidades')
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})

it('error de carga con «Reintentar»', async () => {
  let attempts = 0
  vi.spyOn(offersApi, 'get').mockImplementation(async (path, params) => {
    if (path === 'becas/catalogos') return catalogs
    if (++attempts === 1) throw new Error('Servicio no disponible')
    return { count: 1, page: params.page, page_size: params.page_size, results: [row(1)] }
  })
  render(<MemoryRouter initialEntries={['/gestion/instituciones']}><App /></MemoryRouter>)
  expect(await screen.findByText('Servicio no disponible')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('Entidad 01')).toBeVisible()
})

it('«Añadir» abre la ventana emergente con foco en el primer campo; Cancelar la cierra y devuelve el foco', async () => {
  open([row(1)])
  await screen.findByText('Entidad 01')
  const add = screen.getByRole('button', { name: 'Añadir entidad oferente' })
  add.focus()
  await userEvent.click(add)
  const dialog = screen.getByRole('dialog', { name: 'Nueva entidad oferente' })
  expect(within(dialog).getByLabelText(/Nombre oficial/)).toHaveFocus()
  expect(within(dialog).getByLabelText(/Sector/)).toBeVisible()
  expect(within(dialog).getByLabelText(/País de la entidad oferente/)).toHaveValue('1') // Ecuador por defecto
  expect(within(dialog).getByLabelText(/Web institucional/)).toBeVisible()
  expect(within(dialog).getByText('Editar un oferente devuelve sus convocatorias a revisión pendiente.')).toBeVisible()
  expect(document.body.style.overflow).toBe('hidden')
  // Solo hay un formulario de entidad: el de la ventana emergente, no una tarjeta al final de la página.
  expect(document.querySelectorAll('.institutions-page > section.profile-card form')).toHaveLength(0)
  await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(add).toHaveFocus()
  expect(document.body.style.overflow).toBe('')
})

it('«Editar» abre el mismo diálogo con los datos; se cierra con Esc y con la X; el foco queda atrapado', async () => {
  open([row(1, 'privado', 'Fundación Uno')])
  await screen.findByText('Fundación Uno')
  await userEvent.click(screen.getByRole('button', { name: 'Editar Fundación Uno' }))
  let dialog = screen.getByRole('dialog', { name: 'Editar entidad oferente' })
  expect(within(dialog).getByLabelText(/Nombre oficial/)).toHaveValue('Fundación Uno')
  expect(within(dialog).getByLabelText(/Sector/)).toHaveValue('privado')
  // Tab desde el último control vuelve al primero (botón Cerrar).
  within(dialog).getByRole('button', { name: 'Cancelar' }).focus()
  await userEvent.tab()
  expect(within(dialog).getByRole('button', { name: 'Cerrar' })).toHaveFocus()
  await userEvent.tab({ shift: true })
  expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toHaveFocus()
  fireEvent.keyDown(dialog, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Editar Fundación Uno' }))
  dialog = screen.getByRole('dialog', { name: 'Editar entidad oferente' })
  await userEvent.click(within(dialog).getByRole('button', { name: 'Cerrar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

it('guardar cierra el diálogo, refresca la lista y avisa «Entidad guardada.»', async () => {
  let rows = [row(1)]
  const get = open(() => rows)
  await screen.findByText('Entidad 01')
  const write = vi.spyOn(offersApi, 'write').mockImplementation(async (path, method, values) => { rows = [...rows, { ...values, id: 2 }]; return { ...values, id: 2 } })
  await userEvent.click(screen.getByRole('button', { name: 'Añadir entidad oferente' }))
  const dialog = screen.getByRole('dialog', { name: 'Nueva entidad oferente' })
  await userEvent.type(within(dialog).getByLabelText(/Nombre oficial/), 'Entidad Nueva')
  await userEvent.selectOptions(within(dialog).getByLabelText(/Sector/), 'publico')
  const calls = get.mock.calls.length
  await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar entidad' }))
  expect(write).toHaveBeenCalledWith('gestion/instituciones', 'POST', expect.objectContaining({ nombre: 'Entidad Nueva', sector: 'publico', pais: 1 }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(await screen.findByText('Entidad guardada.')).toBeVisible()
  expect(await screen.findByText('Entidad Nueva')).toBeVisible()
  expect(get.mock.calls.length).toBeGreaterThan(calls)
})

it('muestra los errores de validación del servidor dentro del diálogo, junto al campo', async () => {
  open([row(1)])
  await screen.findByText('Entidad 01')
  vi.spyOn(offersApi, 'write').mockRejectedValue(Object.assign(new Error('Revisa los datos marcados.'), { fields: { nombre: ['Ya existe una entidad con ese nombre.'] } }))
  await userEvent.click(screen.getByRole('button', { name: 'Editar Entidad 01' }))
  const dialog = screen.getByRole('dialog', { name: 'Editar entidad oferente' })
  await userEvent.click(within(dialog).getByRole('button', { name: 'Guardar entidad' }))
  expect(await within(dialog).findByText('Revisa los datos marcados.')).toBeVisible()
  expect(within(dialog).getByText('Ya existe una entidad con ese nombre.')).toBeVisible()
  expect(within(dialog).getByLabelText(/Nombre oficial/)).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.queryByText('Entidad guardada.')).not.toBeInTheDocument()
})
