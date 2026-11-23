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


const conConteos = (r, publicas = 0, borradores = 0) => ({ ...r, convocatorias_publicas: publicas, borradores_privados: borradores })
const BLOQUEO_409 = 'No se puede eliminar: la entidad tiene 1 convocatoria en el catálogo público. Despublica o reasigna esas convocatorias antes.'

it('«Eliminar» nunca está deshabilitado, con o sin convocatorias públicas', async () => {
  open([conConteos(row(1, 'publico', 'Entidad Pública'), 2), conConteos(row(2, 'privado', 'Entidad Libre'))])
  await screen.findByText('2 entidades')
  for (const name of ['Eliminar Entidad Pública', 'Eliminar Entidad Libre']) {
    const button = screen.getByRole('button', { name })
    expect(button).toBeEnabled()
    expect(button).not.toHaveAttribute('aria-disabled')
    expect(button).not.toHaveAttribute('title')
    expect(button).toHaveClass('institution-delete')
  }
})

it('con convocatorias públicas explica el motivo, lista los títulos y solo ofrece «Entendido», sin llamar al DELETE', async () => {
  const muestra = [{ id: 31, titulo: 'Beca pública uno' }, { id: 32, titulo: 'Beca pública dos' }]
  const get = open([conConteos(row(1, 'publico', 'Entidad Pública'), 2)])
  get.mockImplementation(async (path, params = {}) => {
    if (path === 'becas/catalogos') return catalogs
    if (path === 'gestion/instituciones/1') return { ...conConteos(row(1, 'publico', 'Entidad Pública'), 2), muestra_publicas: muestra }
    return { count: 1, page: params.page, page_size: params.page_size, results: [conConteos(row(1, 'publico', 'Entidad Pública'), 2)] }
  })
  const write = vi.spyOn(offersApi, 'write')
  await screen.findByText('Entidad Pública')
  const eliminar = screen.getByRole('button', { name: 'Eliminar Entidad Pública' })
  eliminar.focus()
  await userEvent.click(eliminar)
  const dialog = screen.getByRole('dialog', { name: 'No se puede eliminar esta entidad' })
  expect(dialog).toHaveAccessibleDescription('Entidad Pública tiene 2 convocatorias en el catálogo público. Despublícalas o reasígnalas a otra entidad antes de eliminarla.')
  expect(await within(dialog).findByRole('link', { name: 'Beca pública uno' })).toHaveAttribute('href', '/gestion/convocatorias/31')
  expect(within(dialog).getByRole('link', { name: 'Beca pública dos' })).toHaveAttribute('href', '/gestion/convocatorias/32')
  expect(get).toHaveBeenCalledWith('gestion/instituciones/1')
  expect(within(dialog).queryByRole('button', { name: 'Sí, eliminar' })).not.toBeInTheDocument()
  const entendido = within(dialog).getByRole('button', { name: 'Entendido' })
  expect(entendido).toHaveFocus()
  await userEvent.click(entendido)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(eliminar).toHaveFocus()
  expect(write).not.toHaveBeenCalled()
})

it('sin convocatorias públicas confirma; se cancela con «Cancelar» y con Esc y devuelve el foco a la fila', async () => {
  open([conConteos(row(1, 'privado', 'Entidad Libre'))])
  await screen.findByText('Entidad Libre')
  const eliminar = screen.getByRole('button', { name: 'Eliminar Entidad Libre' })
  eliminar.focus()
  await userEvent.click(eliminar)
  let dialog = screen.getByRole('dialog', { name: 'Eliminar entidad oferente' })
  expect(dialog).toHaveAccessibleDescription('¿Seguro que quieres eliminar Entidad Libre? Esta acción no se puede deshacer.')
  expect(within(dialog).queryByText(/Oferente por confirmar/)).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: 'Sí, eliminar' })).toHaveClass('button-danger')
  expect(within(dialog).getByRole('button', { name: 'Cancelar' })).toHaveFocus()
  await userEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(eliminar).toHaveFocus()
  await userEvent.click(eliminar)
  dialog = screen.getByRole('dialog', { name: 'Eliminar entidad oferente' })
  fireEvent.keyDown(dialog, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(eliminar).toHaveFocus()
})

it('confirmar elimina, refresca la lista y avisa de los borradores desvinculados', async () => {
  let rows = [conConteos(row(1, 'privado', 'Entidad con borradores'), 0, 2), conConteos(row(2))]
  open(() => rows)
  await screen.findByText('Entidad con borradores')
  let resolver
  const write = vi.spyOn(offersApi, 'write').mockImplementation(() => new Promise(resolve => { resolver = resolve }))
  await userEvent.click(screen.getByRole('button', { name: 'Eliminar Entidad con borradores' }))
  const dialog = screen.getByRole('dialog', { name: 'Eliminar entidad oferente' })
  expect(within(dialog).getByText('2 borradores quedarán sin entidad y pasarán a «Oferente por confirmar».')).toBeVisible()
  const confirmar = within(dialog).getByRole('button', { name: 'Sí, eliminar' })
  await userEvent.click(confirmar)
  expect(confirmar).toBeDisabled() // estado de carga: evita el doble clic
  await userEvent.click(confirmar)
  expect(write).toHaveBeenCalledTimes(1)
  expect(write).toHaveBeenCalledWith('gestion/instituciones/1', 'DELETE')
  rows = rows.filter(r => r.id !== 1)
  resolver({ borradores_desvinculados: 2 })
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(await screen.findByText('Entidad eliminada. 2 borradores quedaron sin entidad y pasaron a «Oferente por confirmar».')).toBeVisible()
  expect(await screen.findByText('1 entidad')).toBeVisible()
  expect(screen.queryByText('Entidad con borradores')).not.toBeInTheDocument()
})

it('al quedar vacía la última página, el paginador retrocede', async () => {
  let rows = Array.from({ length: 26 }, (_, i) => conConteos(row(i + 1)))
  open(() => rows)
  await screen.findByText('26 entidades')
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(screen.getByText('26–26 de 26')).toBeVisible()
  vi.spyOn(offersApi, 'write').mockImplementation(async () => { rows = rows.slice(0, 25); return { borradores_desvinculados: 0 } })
  await userEvent.click(screen.getByRole('button', { name: 'Eliminar Entidad 26' }))
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, eliminar' }))
  expect(await screen.findByText('Entidad eliminada.')).toBeVisible()
  expect(await screen.findByText('25 entidades')).toBeVisible()
  expect(screen.getByText('Entidad 01')).toBeVisible()
  expect(screen.queryByRole('navigation', { name: 'Paginación de oferentes' })).not.toBeInTheDocument()
})

it('un 409 inesperado convierte el diálogo al modo «No se puede eliminar» con el mensaje del servidor', async () => {
  open([conConteos(row(1, 'privado', 'Entidad Desactualizada'))])
  await screen.findByText('Entidad Desactualizada')
  vi.spyOn(offersApi, 'write').mockRejectedValue(Object.assign(new Error(BLOQUEO_409), {
    status: 409, fields: { detail: BLOQUEO_409, convocatorias_publicas: 1, muestra_publicas: [{ id: 40, titulo: 'Beca publicada hace un momento' }] } }))
  await userEvent.click(screen.getByRole('button', { name: 'Eliminar Entidad Desactualizada' }))
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Sí, eliminar' }))
  const dialog = await screen.findByRole('dialog', { name: 'No se puede eliminar esta entidad' })
  expect(dialog).toHaveAccessibleDescription(BLOQUEO_409)
  expect(within(dialog).getByRole('link', { name: 'Beca publicada hace un momento' })).toHaveAttribute('href', '/gestion/convocatorias/40')
  expect(within(dialog).queryByRole('button', { name: 'Sí, eliminar' })).not.toBeInTheDocument()
  expect(within(dialog).getByRole('button', { name: 'Entendido' })).toHaveFocus()
  expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument() // sin error genérico
  expect(screen.getByText('Entidad Desactualizada')).toBeInTheDocument()
  expect(screen.queryByText('Entidad eliminada.')).not.toBeInTheDocument()
})
