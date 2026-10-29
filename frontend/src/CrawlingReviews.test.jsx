import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { offersApi } from './api/client'
import CrawlingReviews from './components/CrawlingReviews'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
function setup({ historical = false } = {}) {
  const reviews = []
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('/documentos') ? { results: [{ id: 31, evidencia_id: 8, rol: 'bases_pdf', mime: 'application/pdf', sha256: 'hash sintético' }], count: 1, page_size: 50 } : { results: reviews, vigentes: reviews.slice(-1), count: reviews.length, page_size: 12, numero: 2, ultima_observada: !historical })
  const write = vi.spyOn(offersApi, 'write').mockImplementation(async (_path, _method, data) => { reviews.push({ ...data, id: 9, administrador: { nombre: 'Administradora sintética' }, creada_en: '2026-10-28T10:00:00Z' }); return reviews.at(-1) })
  render(<CrawlingReviews publication={4} version={7} />)
  return write
}

it('registra sobre versión exacta, actualiza decisiones y cancela sin escribir', async () => {
  const write = setup()
  await userEvent.click(await screen.findByRole('button', { name: 'Registrar revisión' }))
  await userEvent.type(screen.getByLabelText('Justificación'), 'Evidencia examinada')
  await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(write).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Registrar revisión' }))
  await userEvent.selectOptions(screen.getByLabelText('Decisión'), 'aprobada')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
  expect(await screen.findByText(/Revisión guardada/)).toBeVisible()
  expect(write).toHaveBeenCalledWith('gestion/rastreo/publicaciones/4/versiones/7/revisiones', 'POST', expect.objectContaining({ motivo: 'Evidencia examinada', sustituye_id: null, evidencia_id: null, decision: 'aprobada' }))
  expect(await screen.findByText(/Extracción: Aprobada/)).toBeVisible()
})

it('mantiene texto y clave tras error recuperable, no muestra éxito y evita envíos duplicados', async () => {
  const write = setup()
  let reject
  write.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
  await userEvent.click(await screen.findByRole('button', { name: 'Registrar revisión' }))
  await userEvent.type(screen.getByLabelText('Justificación'), 'Texto conservado')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
  expect(screen.getByRole('button', { name: 'Guardar revisión' })).toBeDisabled()
  reject(new Error('Fallo sintético'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Fallo sintético')
  expect(screen.getByLabelText('Justificación')).toHaveValue('Texto conservado')
  expect(screen.queryByText(/Revisión guardada/)).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(2))
  expect(write.mock.calls[0][2].clave_accion).toBe(write.mock.calls[1][2].clave_accion)
})

it('distingue evidencia histórica y envía relación documental, no ID global de documento', async () => {
  const write = setup({ historical: true })
  expect(await screen.findByText(/Evidencia histórica/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Registrar revisión' }))
  await userEvent.selectOptions(screen.getByLabelText('Dimensión'), 'documental')
  await userEvent.selectOptions(screen.getByLabelText('Evidencia exacta'), '8')
  await userEvent.type(screen.getByLabelText('Justificación'), 'Página examinada')
  expect(screen.getByText(/Destino: versión 2, documento 31/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar revisión' }))
  expect(write).toHaveBeenCalledWith(expect.any(String), 'POST', expect.objectContaining({ dimension: 'documental', evidencia_id: 8 }))
})
