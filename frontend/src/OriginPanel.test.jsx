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
