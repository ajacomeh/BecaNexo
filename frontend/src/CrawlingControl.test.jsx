import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import CrawlingControl from './components/CrawlingControl'
import { remaining } from './components/crawlTime'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const ready = { fuente_id: 1, politica_version: 'siau-nacionales/3', frecuencia_min: 1440,
  proxima_ejecucion: null, ejecucion_activa: null, inicio_pendiente: false, puede_iniciar: true,
  ultima_ejecucion: { id: 5, estado: 'finalizada', origen: 'programada' } }
function open() { render(<MemoryRouter><CrawlingControl /></MemoryRouter>) }

it('muestra frecuencia, historial y deshabilita el botón antes de la próxima ventana', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, proxima_ejecucion: '2026-11-11T19:43:41Z', puede_iniciar: false })
  open()
  expect(await screen.findByText(/Frecuencia: cada 24 horas \(1440 minutos\)/)).toBeVisible()
  expect(screen.getByRole('region', { name: 'Rastreo automático' })).toBeVisible()
  expect(screen.getByRole('region', { name: 'Rastreo manual' })).toBeVisible()
  expect(within(screen.getByRole('region', { name: 'Rastreo manual' })).getByText(/pendiente de autorización/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Iniciar rastreo' })).toBeDisabled()
  expect(screen.getByRole('link', { name: '#5' })).toHaveAttribute('href', '/gestion/rastreo/ejecuciones/5')
  expect(get).toHaveBeenCalledWith('gestion/rastreo/control')
})

it('solicita inicio con CSRF a través del cliente existente y sigue el estado', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValueOnce(ready).mockResolvedValue({ ...ready, puede_iniciar: false, inicio_pendiente: true })
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ estado: 'iniciando', clave: 'uuid-prueba' })
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Iniciar rastreo' }))
  expect(screen.getByRole('dialog', { name: 'Confirmar inicio de rastreo' })).toBeVisible()
  await userEvent.type(screen.getByLabelText(/Motivo administrativo/), 'Comprobación administrativa')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar inicio' }))
  expect(write).toHaveBeenCalledWith('gestion/rastreo/control', 'POST', { motivo: 'Comprobación administrativa' })
  expect(await screen.findByText(/Inicio solicitado/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Iniciar rastreo' })).toBeDisabled()
  expect(get).toHaveBeenCalledTimes(2)
})

it('informa errores de consulta sin presentar una captura ficticia', async () => {
  vi.spyOn(offersApi, 'get').mockRejectedValue(new Error('Sin conexión de prueba'))
  open()
  expect(await screen.findByText('Sin conexión de prueba')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Iniciar rastreo' })).toBeDisabled()
})

it('conserva el error de inicio tras refrescar la frecuencia', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(ready)
  vi.spyOn(offersApi, 'write').mockRejectedValue(new Error('Inicio rechazado por frecuencia'))
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Iniciar rastreo' }))
  await userEvent.type(screen.getByLabelText(/Motivo administrativo/), 'Comprobación administrativa')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar inicio' }))
  expect(await screen.findByText('Inicio rechazado por frecuencia')).toBeVisible()
})

it('exige motivo, permite cancelar y muestra la espera manual sin iniciar por estimación local', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(ready)
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ estado: 'iniciando' })
  open()
  await userEvent.click(await screen.findByRole('button', { name: 'Iniciar rastreo' }))
  expect(screen.getByRole('button', { name: 'Confirmar inicio' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(write).not.toHaveBeenCalled()
  cleanup()
  vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false,
    rastreo_extraordinario_habilitado: true, proxima_manual: new Date(Date.now() + 275000).toISOString() })
  open()
  expect(await screen.findByText(/Disponible en 4 min/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Iniciar rastreo' })).toBeDisabled()
})

it('expresa horas, minutos, segundos y fechas vencidas sin valores negativos', () => {
  const now = Date.UTC(2026, 10, 11, 12, 0, 0)
  expect(remaining(new Date(now + (22 * 3600 + 41 * 60) * 1000).toISOString(), now)).toBe('22 h 41 min')
  expect(remaining(new Date(now + (35 * 60 + 20) * 1000).toISOString(), now)).toBe('35 min 20 s')
  expect(remaining(new Date(now + 45_000).toISOString(), now)).toBe('45 s')
  expect(remaining(new Date(now - 60_000).toISOString(), now)).toBe('0 s')
})

it('solo presenta Disponible cuando el servidor habilita el inicio', async () => {
  const past = new Date(Date.now() - 60_000).toISOString()
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, proxima_manual: past,
    rastreo_extraordinario_habilitado: false, puede_iniciar: false })
  open()
  expect(await screen.findByText(/La excepción de cinco minutos no está autorizada/)).toBeVisible()
  expect(screen.queryByText('Inicio desde el panel: Disponible')).not.toBeInTheDocument()
  cleanup()
  get.mockResolvedValue({ ...ready, proxima_manual: past, rastreo_extraordinario_habilitado: true })
  open()
  expect(await screen.findByText('Inicio desde el panel: Disponible')).toBeVisible()
})

it('distingue ejecución activa, recuperación pendiente y bloqueo de la fuente', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false, ejecucion_activa: 7 })
  open()
  expect(await screen.findByText('Inicio desde el panel: Hay un rastreo en curso.')).toBeVisible()
  cleanup()
  get.mockResolvedValue({ ...ready, puede_iniciar: false, requiere_revision: true })
  open()
  expect(await screen.findByText(/Pendiente de recuperación/)).toBeVisible()
  cleanup()
  get.mockResolvedValue({ ...ready, puede_iniciar: false, bloqueo_fuente: true })
  open()
  expect(await screen.findByText(/fuente requiere revisión tras una respuesta HTTP 429\/503/)).toBeVisible()
})

it('distingue una omisión por frecuencia y un fallo del trabajador', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false,
    ultimo_inicio_web: { estado: 'omitida_frecuencia' } })
  open()
  expect(await screen.findByText(/Último inicio desde el panel: omitido por frecuencia/)).toBeVisible()
  get.mockResolvedValue({ ...ready, puede_iniciar: false,
    ultimo_inicio_web: { estado: 'fallo_infraestructura' } })
  cleanup()
  open()
  expect(await screen.findByText(/Último inicio desde el panel: fallo del proceso local/)).toBeVisible()
})

it('señala un marcador antiguo para revisión sin ofrecer otro inicio', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false,
    inicio_pendiente: true, requiere_revision: true, ultima_ejecucion: { id: 7, estado: 'en_curso' } })
  open()
  expect(await screen.findByText(/más de dos minutos sin cierre/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Iniciar rastreo' })).toBeDisabled()
})
