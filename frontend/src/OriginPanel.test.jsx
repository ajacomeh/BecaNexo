import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import OriginPanel from './components/OriginPanel'
import { offersApi } from './api/client'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const origin = { aplicacion: { propuesta_id: 3 }, publicacion_id: 4, version_id: 5,
  observacion_base_id: 6, version_convocatoria: 1, hash_convocatoria: 'a'.repeat(64),
  estado: { bloqueos: [], pendientes: [{ id: 'SIN_OPCIONES:opciones', codigo: 'SIN_OPCIONES',
    campo: 'opciones', motivo: 'Falta una opción confirmada' }] }, resoluciones: [] }

it('conserva la justificación y la evidencia ante un error y permite reintentar', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 1, results: [{ evidencia_id: 8, rol: 'bases_pdf' }] } : origin)
  const write = vi.spyOn(offersApi, 'write').mockRejectedValueOnce(new Error('Conflicto de versión'))
    .mockResolvedValueOnce({ id: 11 })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1 }} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Pendiente'), 'SIN_OPCIONES:opciones')
  await user.selectOptions(screen.getByLabelText('Evidencia documental revisada'), '8')
  await user.type(screen.getByLabelText('Justificación y comprobación'), 'Opción cotejada con bases')
  await user.click(screen.getByRole('button', { name: 'Registrar resolución' }))
  expect(await screen.findByText(/Conflicto de versión/)).toBeVisible()
  expect(screen.getByLabelText('Justificación y comprobación')).toHaveValue('Opción cotejada con bases')
  expect(screen.getByLabelText('Evidencia documental revisada')).toHaveValue('8')
  await user.click(screen.getByRole('button', { name: 'Registrar resolución' }))
  expect(await screen.findByText(/Resolución registrada/)).toBeVisible()
  expect(write).toHaveBeenCalledTimes(2)
})

it('no presenta procedencia en una convocatoria manual', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ aplicacion: null })
  render(<MemoryRouter><OriginPanel offer={{ id: 9, version: 1 }} /></MemoryRouter>)
  await waitFor(() => expect(screen.queryByText('Consultando origen…')).not.toBeInTheDocument())
  expect(screen.queryByText('Registrar resolución comprobada')).not.toBeInTheDocument()
})

it('muestra origen automático, pendientes y oferente sugerido sin asignarlo', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ aplicacion: null, automatico: true,
    publicacion_id: 15, version_id: 23,
    bloqueos_actuales: ['Confirmar oferente ecuatoriano'],
    datos_iniciales: { titulo: 'Beca nacional sintética', entidad_sugerida: { id: 4, nombre: 'Entidad sintética' } } })
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 1 }} /></MemoryRouter>)
  expect(await screen.findByText('Borrador generado por rastreo')).toBeVisible()
  expect(screen.getByText('Confirmar oferente ecuatoriano')).toBeVisible()
  expect(screen.getByRole('link', { name: /Consultar ficha/ })).toHaveAttribute('href', '/gestion/rastreo/publicaciones/15')
  await userEvent.setup().click(screen.getByText('Datos de origen conservados'))
  expect(screen.getByText(/Entidad sintética \(ID 4; confirmar antes de asignar\)/)).toBeVisible()
})

it('avisa de una versión relevante y confirma su revisión sin aplicar datos automáticamente', async () => {
  const current = { aplicacion: null, automatico: true, publicacion_id: 15,
    version_id: 23, version_actual_id: 24, version_convocatoria: 3,
    cambio_relevante: true, revision_confirmada: false,
    bloqueos_actuales: ['Confirmar versión 24'], datos_iniciales: { titulo: 'Ficha original' } }
  vi.spyOn(offersApi, 'get').mockResolvedValue(current)
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({})
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 3 }} /></MemoryRouter>)
  expect(await screen.findByText(/versión 24 contiene cambios posteriores/)).toBeVisible()
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Motivo de revisión de la nueva versión'), 'Comparé la ficha y conservo el título editado.')
  await user.click(screen.getByRole('button', { name: 'Confirmar versión revisada' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/rastreo/convocatorias/11/origen', 'POST',
    { version_id: 24, version_convocatoria: 3, motivo: 'Comparé la ficha y conservo el título editado.' }))
})

it('muestra la correspondencia estable entre candidato y opción sin confundir alternativas iguales', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 0, results: [] } : { ...origin,
      aplicacion: { propuesta_id: 3, opciones_ids: { o1: 11, o2: 12 } },
      estado: { bloqueos: [], pendientes: [] },
      resoluciones: [{ id: 15, pendiente_id: 'opciones.o3', motivo: 'Revisión exacta',
        evidencia_id: 8, opcion_candidata_id: 'o3', opcion_estudio_id: 13 }] })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1,
    opciones: [{ id: 11, programa: 'Programa compartido' }, { id: 12, programa: 'Programa compartido' }] }} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(await screen.findByText('Correspondencias de opciones creadas'))
  expect(screen.getByText(/Candidato o1 → opción 11: Programa compartido/)).toBeVisible()
  expect(screen.getByText(/Candidato o2 → opción 12: Programa compartido/)).toBeVisible()
  await user.click(screen.getByText('Resoluciones registradas'))
  expect(screen.getByText(/Candidato o3 → opción 13/)).toBeVisible()
})

it('permite revisar cierre por día y tope, pero mantiene pendiente la apertura sin hora', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 0, results: [] } : { ...origin, estado: { bloqueos: [], pendientes: [
      { id: 'fecha', codigo: 'PRECISION_TEMPORAL', campo: 'cierre_original', motivo: 'Hora desconocida' },
      { id: 'tope', codigo: 'TOPE_NO_REPRESENTADO', campo: 'beneficios.b1', motivo: 'Tope por revisar' },
      { id: 'apertura', codigo: 'PRECISION_TEMPORAL', campo: 'apertura_original', motivo: 'Apertura sin hora' },
    ] } })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1 }} /></MemoryRouter>)
  const selector = await screen.findByLabelText('Pendiente')
  expect(selector.querySelector('option[value="fecha"]')).not.toBeDisabled()
  expect(selector.querySelector('option[value="tope"]')).not.toBeDisabled()
  expect(selector.querySelector('option[value="apertura"]')).toBeDisabled()
})
