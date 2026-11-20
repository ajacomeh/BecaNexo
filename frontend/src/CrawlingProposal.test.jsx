import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import CrawlingProposal from './components/CrawlingProposal'
import { offersApi } from './api/client'
import { MemoryRouter } from 'react-router-dom'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
function setup(initialRows = [], html = false) {
  const rows = [...initialRows]
  const context = { version_id: 2, observacion_base_id: 3, revisiones: [] }
  const pending = { bloqueos: [], pendientes_publicacion: [], creacion_habilitada: false }
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? { paises: [{ codigo: 'EC', nombre: 'Ecuador' }, { codigo: 'PE', nombre: 'Perú' }] } : path.endsWith('/documentos') ? { results: [{ id: 77, evidencia_id: 8, rol: html ? 'ficha_html' : 'bases_pdf' }], count: 1, page_size: 50 } : path.endsWith('/versiones/2') ? { datos_extraidos: { titulo: { texto_original: 'Título extraído' } } } : { results: rows, count: rows.length, page_size: 12, contexto: context })
  const write = vi.spyOn(offersApi, 'write').mockImplementation(async (path, _method, body) => {
    if (path.endsWith('/validar')) return { actual: pending, guardado: pending, contexto_cambio: true }
    const row = { ...body, id: rows.length + 1, autor: { nombre: 'Administración sintética' }, pendientes: pending }
    rows.unshift(row); return row
  })
  render(<MemoryRouter><CrawlingProposal publication={1} /></MemoryRouter>)
  return write
}

it('permite aplicar un campo revisado al borrador vinculado sin crear otra convocatoria', async () => {
  const proposal = { id: 9, hash_propuesta: 'a'.repeat(64), version_id: 2,
    observacion_base_id: 3, revisiones: [], datos: { titulo: 'Título revisado' },
    procedencia: [{ campo: 'titulo', evidencia_id: 8, localizador: 'Ficha', motivo: 'Revisado' }],
    pendientes: { bloqueos: [], pendientes_publicacion: [], creacion_habilitada: false },
    autor: { nombre: 'Administrador' } }
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path === 'gestion/rastreo/publicaciones/1/propuesta') return {
      results: [proposal], count: 1, page_size: 12, borrador_automatico_id: 7,
      contexto: { version_id: 2, observacion_base_id: 3, revisiones: [] } }
    if (path === 'gestion/instituciones') return { results: [], count: 0, page_size: 50 }
    if (path === 'becas/catalogos') return { paises: [], tipos_requisito: [] }
    if (path === 'gestion/convocatorias/7') return { id: 7, version: 1, titulo: 'Título original' }
    if (path.endsWith('/documentos')) return { results: [{ id: 8, evidencia_id: 8, rol: 'ficha_html' }], count: 1, page_size: 50 }
    if (path.endsWith('/versiones/2')) return { datos_extraidos: {} }
    throw new Error(`Ruta inesperada: ${path}`)
  })
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ id: 7, version: 2, titulo: 'Título revisado' })
  render(<MemoryRouter><CrawlingProposal publication={1} /></MemoryRouter>)
  expect(await screen.findByText(/Borrador privado del rastreo vinculado/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Continuar propuesta' }))
  expect(await screen.findByText('Aplicar cambios al borrador vinculado')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Crear borrador/ })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('checkbox', { name: /Título:/ }))
  await userEvent.type(screen.getByLabelText('Motivo de la aplicación'), 'Confirmé el título frente a la ficha.')
  await userEvent.click(screen.getByRole('button', { name: 'Aplicar campos seleccionados' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/rastreo/propuestas/9/aplicar-borrador', 'POST', {
    version_convocatoria: 1, hash_propuesta: 'a'.repeat(64), campos: ['titulo'],
    motivo: 'Confirmé el título frente a la ficha.',
  }))
})

it('propone tipo, cobertura, gastos, bases y apertura con hora y los ofrece para aplicar', async () => {
  const proposal = { id: 9, hash_propuesta: 'b'.repeat(64), version_id: 2, observacion_base_id: 3, revisiones: [],
    datos: { tipo_beca: 4, cobertura_tipo: 'parcial', apertura: '2026-12-01T08:00:00-05:00' }, procedencia: [],
    pendientes: { bloqueos: [], pendientes_publicacion: [], creacion_habilitada: false }, autor: { nombre: 'Administrador' } }
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path === 'gestion/rastreo/publicaciones/1/propuesta') return { results: [proposal], count: 1, page_size: 12,
      borrador_automatico_id: 7, contexto: { version_id: 2, observacion_base_id: 3, revisiones: [] } }
    if (path === 'gestion/instituciones') return { results: [], count: 0, page_size: 50 }
    if (path === 'becas/catalogos') return { paises: [], tipos_requisito: [], tipos_beca: [{ id: 4, nombre: 'Socioeconómica' }] }
    if (path === 'gestion/convocatorias/7') return { id: 7, version: 1, tipo_beca: null }
    if (path.endsWith('/documentos')) return { results: [{ id: 8, evidencia_id: 8, rol: 'ficha_html' }], count: 1, page_size: 50 }
    if (path.endsWith('/versiones/2')) return { datos_extraidos: {} }
    throw new Error(`Ruta inesperada: ${path}`)
  })
  const write = vi.spyOn(offersApi, 'write').mockImplementation(async (_path, _method, body) => ({ ...proposal, ...body, id: 9 }))
  render(<MemoryRouter><CrawlingProposal publication={1} /></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: 'Continuar propuesta' }))
  expect(screen.getByLabelText('Tipo de beca')).toHaveValue('4')
  expect(screen.getByLabelText('Apertura con hora confirmada (America/Guayaquil)')).toHaveValue('2026-12-01T08:00')
  expect(screen.getByRole('checkbox', { name: /Tipo de beca: Pendiente → Socioeconómica/ })).toBeVisible()
  expect(screen.getByRole('checkbox', { name: /Cobertura:/ })).toBeVisible()
  await userEvent.type(screen.getByLabelText('Enlace de las bases'), 'https://example.org/bases.pdf')
  await userEvent.type(screen.getByLabelText('Gastos no cubiertos'), 'Pasajes')
  await userEvent.clear(screen.getByLabelText('Apertura con hora confirmada (America/Guayaquil)'))
  await userEvent.click(screen.getByRole('button', { name: 'Guardar propuesta' }))
  await waitFor(() => expect(write).toHaveBeenCalled())
  expect(write.mock.calls[0][2].datos).toEqual({ tipo_beca: 4, cobertura_tipo: 'parcial', apertura: '',
    url_bases: 'https://example.org/bases.pdf', gastos_no_cubiertos: 'Pasajes' })
})

it('guarda propuesta incompleta, consulta historial y valida sin crear convocatoria', async () => {
  const write = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.clear(screen.getByLabelText('Título propuesto'))
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
  await userEvent.clear(screen.getByLabelText('Título propuesto'))
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
  await userEvent.clear(screen.getByLabelText('Título propuesto'))
  await userEvent.type(screen.getByLabelText('Título propuesto'), 'Pendiente')
  await userEvent.click(screen.getByRole('button', { name: 'Añadir referencia' }))
  await userEvent.click(screen.getByText(/Referencia 1 · Campo pendiente/))
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

it('conserva la propuesta previa y actualiza el contexto sin sobrescribir sus valores', async () => {
  const existing = { id: 12, version_id: 2, observacion_base_id: 3, revisiones: [],
    datos: { titulo: 'Título editado por administración', descripcion: 'Texto administrativo' }, procedencia: [],
    pendientes: { bloqueos: [], pendientes_publicacion: [] }, autor: { nombre: 'Administración' } }
  const write = setup([existing], true)
  await userEvent.click(await screen.findByRole('button', { name: 'Continuar propuesta' }))
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título editado por administración')
  expect(screen.getByLabelText('Descripción propuesta')).toHaveValue('Texto administrativo')
  expect(screen.queryByRole('button', { name: 'Sugerir en campos vacíos' })).not.toBeInTheDocument()
  expect(screen.queryByText('Sugerencias de la ficha')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar contexto conservando valores' }))
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título editado por administración')
  expect(screen.getByLabelText('Descripción propuesta')).toHaveValue('Texto administrativo')
  expect(write).not.toHaveBeenCalled()
})

it('precarga automáticamente un snapshot anterior vacío sin modificarlo hasta guardar', async () => {
  const existing = { id: 13, version_id: 2, observacion_base_id: 3, revisiones: [], datos: {}, procedencia: [],
    pendientes: { bloqueos: [], pendientes_publicacion: [] }, autor: { nombre: 'Administración' } }
  const write = setup([existing], true)
  await userEvent.click(await screen.findByRole('button', { name: 'Continuar propuesta' }))
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título extraído')
  expect(screen.getByText(/Referencia 1 · titulo/).closest('details')).not.toHaveAttribute('open')
  await userEvent.click(screen.getByText(/Referencia 1 · titulo/))
  expect(screen.getByLabelText('Documento exacto')).toHaveValue('8')
  await userEvent.click(screen.getByRole('button', { name: 'Retirar referencia' }))
  expect(screen.queryByText(/Referencia 1 · titulo/)).not.toBeInTheDocument()
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título extraído')
  expect(write).not.toHaveBeenCalled()
})

it('precarga una propuesta nueva sin mostrar tarjeta duplicada ni exigir otro botón', async () => {
  const write = setup([], true)
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título extraído')
  expect(screen.queryByText('Sugerencias de la ficha')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Sugerir en campos vacíos' })).not.toBeInTheDocument()
  expect(write).not.toHaveBeenCalled()
})

it('al cambiar de versión conserva lo editado y solo completa campos nuevos de la nueva evidencia', async () => {
  const write = setup([], true)
  const get = vi.mocked(offersApi.get)
  const initial = get.getMockImplementation()
  let changed = false
  get.mockImplementation(async (path, params) => {
    if (path.endsWith('/propuesta')) {
      if (changed) return { results: [], count: 0, page_size: 12,
        contexto: { version_id: 3, observacion_base_id: 4, revisiones: [] } }
    }
    if (path.endsWith('/versiones/3')) return { datos_extraidos: {
      titulo: { texto_original: 'Título cambiado en la fuente' },
      descripcion: { texto_original: 'Descripción nueva verificable' },
    } }
    return initial(path, params)
  })
  await userEvent.click(await screen.findByRole('button', { name: 'Crear propuesta' }))
  await userEvent.clear(screen.getByLabelText('Título propuesto'))
  await userEvent.type(screen.getByLabelText('Título propuesto'), 'Título revisado por administración')
  changed = true
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar contexto conservando valores' }))
  await screen.findByText(/Contexto actualizado sin sobrescribir valores/)
  expect(screen.getByLabelText('Título propuesto')).toHaveValue('Título revisado por administración')
  expect(screen.getByLabelText('Descripción propuesta')).toHaveValue('Descripción nueva verificable')
  expect(screen.getByText(/Referencia 1 · titulo/)).toHaveTextContent('Documento pendiente · Versión 3')
  expect(write).not.toHaveBeenCalled()
})
