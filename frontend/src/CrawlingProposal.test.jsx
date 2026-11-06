import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CrawlingProposal from './components/CrawlingProposal'
import { offersApi } from './api/client'
import { MemoryRouter } from 'react-router-dom'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
function setup() {
  const rows = []
  const context = { version_id: 2, observacion_base_id: 3, revisiones: [] }
  const pending = { bloqueos: [], pendientes_publicacion: [], creacion_habilitada: false }
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? { paises: [{ codigo: 'EC', nombre: 'Ecuador' }, { codigo: 'PE', nombre: 'Perú' }] } : path.endsWith('/documentos') ? { results: [{ id: 77, evidencia_id: 8, rol: 'bases_pdf' }], count: 1, page_size: 50 } : path.endsWith('/versiones/2') ? { datos_extraidos: { titulo: { texto_original: 'Título extraído' } } } : { results: rows, count: rows.length, page_size: 12, contexto: context })
  const write = vi.spyOn(offersApi, 'write').mockImplementation(async (path, _method, body) => {
    if (path.endsWith('/validar')) return { actual: pending, guardado: pending, contexto_cambio: true }
    const row = { ...body, id: rows.length + 1, autor: { nombre: 'Administración sintética' }, pendientes: pending }
    rows.unshift(row); return row
  })
  render(<MemoryRouter><CrawlingProposal publication={1} /></MemoryRouter>)
  return write
}

it('guarda propuesta incompleta, consulta historial y valida sin crear convocatoria', async () => {
  const write = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.type(screen.getByLabelText('Título propuesto'), 'Título pendiente')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  expect(await screen.findByText(/Propuesta guardada fuera del catálogo/)).toBeVisible()
  expect(write).toHaveBeenCalledWith(expect.stringContaining('/propuesta'), 'POST', expect.objectContaining({ datos: { titulo: 'Título pendiente' } }))
  await userEvent.click(await screen.findByRole('button', { name: 'Consultar revisión de propuesta 1' }))
  expect(screen.getByText('Snapshot histórico 1')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Validar propuesta' }))
  expect(await screen.findByText(/El contexto cambió/)).toBeVisible()
})

it('conserva texto y clave al reintentar y cambia clave en una edición intencional', async () => {
  const write = setup()
  write.mockRejectedValueOnce(new Error('Fallo sintético'))
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.type(screen.getByLabelText('Título propuesto'), 'Conservar')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Fallo sintético')
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Conservar')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(2))
  expect(write.mock.calls[0][2].clave_accion).toBe(write.mock.calls[1][2].clave_accion)
  await userEvent.type(screen.getByLabelText('Título propuesto'), ' nuevo')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  expect(write.mock.calls[2][2].clave_accion).not.toBe(write.mock.calls[1][2].clave_accion)
})

it('mantiene valores ante conflicto y utiliza relación documental exacta', async () => {
  const write = setup()
  write.mockRejectedValueOnce(Object.assign(new Error('Conflicto'), { status: 409 }))
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.type(screen.getByLabelText('Título propuesto'), 'Pendiente')
  await userEvent.click(screen.getByRole('button', { name: 'Añadir referencia' }))
  await userEvent.selectOptions(screen.getByLabelText('Documento exacto'), '8')
  await userEvent.type(screen.getByLabelText('Campo o identificador del elemento'), 'titulo')
  await userEvent.type(screen.getByLabelText('Página o sección'), 'p1')
  await userEvent.type(screen.getByLabelText('Motivo de la transcripción o corrección'), 'Transcripción')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Consulta el historial')
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Pendiente')
  expect(write.mock.calls[0][2].procedencia[0].evidencia_id).toBe(8)
})

it('mantiene ámbito pendiente y permite elegir solo destinos de la opción sin borrar referencias al editar', async () => {
  const write = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.click(screen.getByRole('button', { name: 'Añadir opciones de estudio' }))
  await userEvent.type(screen.getByLabelText('Programa o mención original'), 'Opción sintética')
  await userEvent.selectOptions(screen.getByLabelText('Países candidatos de esta opción'), 'EC')
  await userEvent.click(screen.getByRole('button', { name: 'Añadir beneficios' }))
  expect(screen.getByLabelText('Ámbito candidato')).toHaveValue('pendiente')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  await screen.findByText(/Propuesta guardada fuera del catálogo/)
  expect(write.mock.calls[0][2].datos.beneficios[0].ambito).toBe('pendiente')
  await userEvent.selectOptions(screen.getByLabelText('Ámbito candidato'), 'destino')
  const option = write.mock.calls[0][2].datos.opciones[0].id
  await userEvent.selectOptions(screen.getByLabelText('Opción candidata'), option)
  await userEvent.selectOptions(screen.getByLabelText('Destino de la opción'), 'EC')
  expect([...screen.getByLabelText('Destino de la opción').options].map((o) => o.value)).not.toContain('PE')
  await userEvent.selectOptions(screen.getByLabelText('Ámbito candidato'), 'pendiente')
  expect(screen.getByLabelText('Opción candidata')).toHaveValue(option)
  expect(screen.getByLabelText('Destino de la opción')).toHaveValue('EC')
})

it('bloquea envíos durante guardado y recupera un fallo de petición', async () => {
  const write = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  let reject
  write.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  expect(screen.getByRole('button', { name: 'Guardar propuesta' })).toBeDisabled()
  expect(screen.getByLabelText('Título propuesto')).toBeDisabled()
  reject(new Error('Error recuperable'))
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Guardar propuesta' })).toBeEnabled()
})
