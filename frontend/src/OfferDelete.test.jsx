import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ApiError, offersApi } from './api/client'
import OfferEditor from './pages/OfferEditor'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
// jsdom no implementa showModal: el aviso se abre como un diálogo normal.
beforeEach(() => { Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true } }) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete HTMLDialogElement.prototype.showModal })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [],
  tipos_requisito: [{ id: 1, codigo: 'EDAD', nombre: 'Edad', esquema_valor: { campos: {} } }],
  niveles: [{ valor: 'maestria', nombre: 'Maestría' }], modalidades: [{ valor: 'virtual', nombre: 'Virtual' }] }

function offer(extra = {}) {
  return { id: 41, titulo: 'Convocatoria sintética', institucion: { id: 1, nombre: 'Entidad' }, revision: 'pendiente', estado: 'borrador',
    activa: true, version: 3,
    opciones: [{ id: 11, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa A', paises: [1], activa: true },
      { id: 12, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa B', paises: [1], activa: true }],
    beneficios: [],
    requisitos: [{ id: 8, tipo_requisito: 1, texto_original: 'Edad máxima de 35 años', activo: true, opcion_estudio: null },
      { id: 9, tipo_requisito: 1, texto_original: 'Edad máxima de 30 años en el Programa A', activo: true, opcion_estudio: 11 }],
    ...extra }
}

function renderEditor(data) {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
    : path === 'gestion/convocatorias/41' ? data : path.endsWith('/origen') ? { aplicacion: null } : { count: 1, results: [{ id: 1, nombre: 'Entidad' }] })
  render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
}

describe('eliminar requisitos y opciones de estudio', () => {
  it('pide confirmación para eliminar un requisito, permite cancelar y luego lo elimina', async () => {
    renderEditor(offer())
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue(null)
    const region = within(await screen.findByRole('region', { name: 'Requisitos' }))
    await userEvent.click(region.getAllByRole('button', { name: 'Eliminar' })[0])
    expect(await screen.findByRole('heading', { name: '¿Seguro que quieres eliminar este requisito?' })).toBeVisible()
    expect(screen.getByText(/Se quitará de la convocatoria el requisito «Edad: Edad máxima de 35 años»/)).toBeVisible()
    expect(screen.getByText(/No se puede deshacer desde esta pantalla/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('heading', { name: '¿Seguro que quieres eliminar este requisito?' })).not.toBeInTheDocument()
    expect(write).not.toHaveBeenCalled()
    await userEvent.click(region.getAllByRole('button', { name: 'Eliminar' })[0])
    await userEvent.click(await screen.findByRole('button', { name: 'Confirmar eliminación' }))
    await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/requisitos/8', 'DELETE'))
    expect(await screen.findByText(/Registro eliminado/)).toBeVisible()
    expect(region.queryByText(/Edad máxima de 35 años/)).not.toBeInTheDocument()
    expect(region.getByText(/Edad máxima de 30 años en el Programa A/)).toBeVisible()
  })

  it('al eliminar una opción lista sus requisitos propios y los quita con ella', async () => {
    renderEditor(offer())
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue(null)
    const options = within(await screen.findByRole('region', { name: 'Opciones de estudio' }))
    await userEvent.click(options.getAllByRole('button', { name: 'Eliminar' })[0])
    expect(await screen.findByRole('heading', { name: '¿Seguro que quieres eliminar esta opción?' })).toBeVisible()
    expect(screen.getByText('También se eliminarán sus requisitos propios:')).toBeVisible()
    const dialog = screen.getByRole('heading', { name: '¿Seguro que quieres eliminar esta opción?' }).closest('dialog')
    expect(within(dialog).getByText('Edad máxima de 30 años en el Programa A')).toBeVisible()
    expect(within(dialog).queryByText('Edad máxima de 35 años')).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Confirmar eliminación' }))
    await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/opciones/11', 'DELETE'))
    expect(options.queryByText(/Programa A/)).not.toBeInTheDocument()
    expect(options.getByText(/Programa B/)).toBeVisible()
    const requirements = within(screen.getByRole('region', { name: 'Requisitos' }))
    expect(requirements.queryByText(/Programa A/)).not.toBeInTheDocument()
    expect(requirements.getByText(/Edad máxima de 35 años/)).toBeVisible()
  })

  it('en una convocatoria publicada avisa que es la última opción activa y muestra el rechazo del servidor', async () => {
    const data = offer({ revision: 'validada', estado: 'abierta',
      opciones: [{ id: 11, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa A', paises: [1], activa: true }], requisitos: [] })
    renderEditor(data)
    const write = vi.spyOn(offersApi, 'write').mockRejectedValue(new ApiError(
      'No se puede eliminar la última opción activa de una convocatoria publicada: publicar exige al menos una opción activa.', 400, {}))
    const options = within(await screen.findByRole('region', { name: 'Opciones de estudio' }))
    await userEvent.click(options.getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByText(/Es la última opción activa de una convocatoria publicada/)).toBeVisible()
    expect(screen.getByText(/volverá a revisión pendiente/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar eliminación' }))
    expect(await screen.findByText(/No se puede eliminar la última opción activa/)).toBeVisible()
    expect(write).toHaveBeenCalledTimes(1)
    // La opción sigue en la lista (el texto también aparece en el aviso, que permanece abierto con el error).
    expect(within(options.getAllByRole('list')[0]).getByText(/Programa A/)).toBeVisible()
  })

  it('avisa de los beneficios propios de la opción y mantiene la eliminación de beneficios', async () => {
    renderEditor(offer({ beneficios: [{ id: 5, concepto: 'Matrícula', opcion_estudio: 12 }] }))
    vi.spyOn(offersApi, 'write').mockResolvedValue(null)
    const options = within(await screen.findByRole('region', { name: 'Opciones de estudio' }))
    await userEvent.click(options.getAllByRole('button', { name: 'Eliminar' })[1])
    expect(await screen.findByText(/Tiene beneficios propios \(Matrícula\)/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    const benefits = within(screen.getByRole('region', { name: 'Beneficios' }))
    await userEvent.click(benefits.getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByRole('heading', { name: '¿Eliminar este beneficio?' })).toBeVisible()
  })
})
