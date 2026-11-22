import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import CrawlingControl from './components/CrawlingControl'
import { remaining } from './components/crawlTime'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const ready = { fuente_id: 1, politica_version: 'siau-nacionales/3', frecuencia_min: 1440,
  fuente_nombre: 'SIAU', fuentes_activas: 1, publicaciones_total: 5, borradores_total: 1,
  fuentes_registradas: [{ id: 1, nombre: 'SIAU', activa: true, utilizable: true, politica_version: 'siau-nacionales/3', frecuencia_min: 1440 }],
  conectores_sin_registro: [{ adaptador: 'portal_ec:utpl', nombre: 'Becas UTPL' }],
  fuentes_configuracion: [{ id: 1, nombre: 'SIAU', politica_version: 'siau-nacionales/3', frecuencia_min: 1440 }],
  proxima_ejecucion: null, ejecucion_activa: null, inicio_pendiente: false, puede_iniciar: true,
  ultima_ejecucion: { id: 5, estado: 'finalizada', origen: 'programada' } }
function open() { render(<MemoryRouter><CrawlingControl /></MemoryRouter>) }
const startButton = () => screen.getByRole('button', { name: 'Iniciar rastreo' })
// aria-disabled en lugar de disabled: el botón sigue siendo enfocable con el teclado y anuncia su motivo.
const expectBlocked = () => expect(startButton()).toHaveAttribute('aria-disabled', 'true')
const expectAvailable = () => expect(startButton()).not.toHaveAttribute('aria-disabled')

it('muestra el bloqueo HTTP 429 y lo levanta con motivo y clave estable al reintentar', async () => {
  const block = { fuente_id: 1, fuente_nombre: 'SIAU', http_status: 429, bloqueado_en: '2026-11-19T15:00:00Z',
    ejecucion_id: 8, reintento_desde: '2026-11-19T15:03:00Z' }
  const get = vi.spyOn(offersApi, 'get').mockResolvedValueOnce({ ...ready, puede_iniciar: false, bloqueo_fuente: true, bloqueos: [block] })
    .mockResolvedValue({ ...ready, bloqueos: [] })
  const write = vi.spyOn(offersApi, 'write').mockRejectedValueOnce(new Error('Fallo sintético')).mockResolvedValue({ creado: true })
  open()
  expect(await screen.findByText(/por una respuesta HTTP 429/)).toBeVisible()
  expect(screen.getByText(/La fuente requiere revisión tras una respuesta HTTP 429\/503/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Levantar bloqueo' }))
  expect(screen.getByRole('button', { name: 'Confirmar desbloqueo' })).toBeDisabled()
  await userEvent.type(screen.getByLabelText(/Motivo del desbloqueo/), 'Revisé la respuesta de la fuente.')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar desbloqueo' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Fallo sintético')
  await userEvent.click(screen.getByRole('button', { name: 'Confirmar desbloqueo' }))
  await screen.findByRole('button', { name: 'Iniciar rastreo' })
  await vi.waitFor(expectAvailable)
  expect(screen.queryByText(/por una respuesta HTTP 429/)).not.toBeInTheDocument()
  expect(write).toHaveBeenCalledTimes(2)
  expect(write.mock.calls[0][0]).toBe('gestion/rastreo/fuentes/1/desbloquear')
  expect(write.mock.calls[0][2]).toEqual({ motivo: 'Revisé la respuesta de la fuente.', clave_accion: write.mock.calls[1][2].clave_accion })
  expect(get).toHaveBeenCalledTimes(2)
})

it('muestra frecuencia, historial y deshabilita el botón antes de la próxima ventana', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, proxima_ejecucion: '2026-11-11T19:43:41Z', puede_iniciar: false })
  open()
  expect(await screen.findByRole('heading', { name: 'Rastreo' })).toBeVisible()
  // El encabezado se muestra antes que el estado; se espera a las métricas cargadas.
  expect((await screen.findByText('Publicaciones detectadas')).nextSibling).toHaveTextContent('5')
  expect(screen.getByText('Borradores automáticos').nextSibling).toHaveTextContent('1')
  await userEvent.click(screen.getByText('Configuración y detalles técnicos'))
  expect(screen.getByText(/SIAU · Activa y autorizada · Política: siau-nacionales\/3 · Frecuencia: 1440 minutos/)).toBeVisible()
  expect(screen.getByText('Las publicaciones no se aprueban automáticamente.')).toBeVisible()
  // Los conectores sin fuente y las notas técnicas ya no se muestran en el panel.
  for (const text of [/Becas UTPL/, /pendiente de autorización/, /conector genérico/, /La tarea automática respeta/, /Descubrimiento de becas/])
    expect(screen.queryByText(text)).not.toBeInTheDocument()
  expectBlocked()
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
  expectBlocked()
  expect(get).toHaveBeenCalledTimes(2)
})

it('informa errores de consulta sin presentar una captura ficticia', async () => {
  vi.spyOn(offersApi, 'get').mockRejectedValue(new Error('Sin conexión de prueba'))
  open()
  expect(await screen.findByText('Sin conexión de prueba')).toBeVisible()
  expectBlocked()
  await userEvent.click(startButton())
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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
  // El motivo de frecuencia no es un recuadro: es la descripción accesible del botón (tooltip).
  expect(await screen.findByText(/Disponible en 4 min/)).toHaveAttribute('role', 'tooltip')
  expect(startButton()).toHaveAccessibleDescription(/Disponible en 4 min .* por frecuencia/)
  expectBlocked()
  expect(screen.getByText(/Próxima disponibilidad: .* · 4 min/)).toBeVisible()
  startButton().focus()
  expect(startButton()).toHaveFocus()
  await userEvent.keyboard('{Enter}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(write).not.toHaveBeenCalled()
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
  expect(await screen.findByText(/la excepción de cinco minutos no está autorizada/)).toHaveAttribute('role', 'tooltip')
  expectBlocked()
  expect(screen.queryByText(/disponible ahora/)).not.toBeInTheDocument()
  cleanup()
  get.mockResolvedValue({ ...ready, proxima_manual: past, rastreo_extraordinario_habilitado: true })
  open()
  expect(await screen.findByText('Próxima disponibilidad: disponible ahora para SIAU')).toBeVisible()
  expectAvailable()
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('distingue ejecución activa, recuperación pendiente y bloqueo de la fuente', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false, ejecucion_activa: 7 })
  open()
  expect(await screen.findByText('Rastreo en curso · ejecución 7.')).toBeVisible()
  expect(screen.getByRole('tooltip')).toHaveTextContent('Hay un rastreo en curso.')
  cleanup()
  get.mockResolvedValue({ ...ready, puede_iniciar: false, requiere_revision: true })
  open()
  expect(await screen.findByRole('tooltip')).toHaveTextContent(/Pendiente de recuperación/)
  cleanup()
  // Una causa distinta de la frecuencia (bloqueo HTTP) sí se muestra a la vista y describe el botón.
  get.mockResolvedValue({ ...ready, puede_iniciar: false, bloqueo_fuente: true })
  open()
  expect(await screen.findByText(/No se puede iniciar: La fuente requiere revisión tras una respuesta HTTP 429\/503/)).toBeVisible()
  expect(startButton()).toHaveAccessibleDescription(/HTTP 429\/503/)
  expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
})

it('distingue una omisión por frecuencia y un fallo del trabajador', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false,
    ultimo_inicio_web: { estado: 'omitida_frecuencia' } })
  open()
  // Una omisión por frecuencia no genera un mensaje visible; un fallo del trabajador sí.
  await screen.findByText(/Próxima disponibilidad/)
  expect(screen.queryByText(/último inicio desde el panel/i)).not.toBeInTheDocument()
  get.mockResolvedValue({ ...ready, puede_iniciar: false,
    ultimo_inicio_web: { estado: 'fallo_infraestructura' } })
  cleanup()
  open()
  expect(await screen.findByText('El último inicio desde el panel no se completó: fallo del proceso local.')).toBeVisible()
})

it('señala un marcador antiguo para revisión sin ofrecer otro inicio', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, puede_iniciar: false,
    inicio_pendiente: true, requiere_revision: true, ultima_ejecucion: { id: 7, estado: 'en_curso' } })
  open()
  expect(await screen.findByText(/más de dos minutos sin cierre/)).toBeVisible()
  expectBlocked()
})

it('resume la última corrida en una sola línea, sin detalles técnicos ni punto doble', async () => {
  const corrida = { ejecucion_id: 12, origen: 'programada', estado: 'finalizada', inicio: '2026-11-21T15:46:08Z', fin: '2026-11-21T15:47:30Z',
    peticiones: 9, publicaciones_observadas: 5, versiones_nuevas: 1, candidatos_nuevos: 2, borradores_creados: 1, incidencias_total: 3, motivo: null }
  vi.spyOn(offersApi, 'get').mockResolvedValue({ ...ready, ultima_ejecucion: { id: 12, estado: 'finalizada', inicio: corrida.inicio }, ultima_programada: corrida })
  open()
  const line = (await screen.findByText(/Última corrida:/)).closest('p')
  expect(within(line).getByRole('link', { name: '#12' })).toHaveAttribute('href', '/gestion/rastreo/ejecuciones/12')
  expect(line).toHaveTextContent(new RegExp(`#12 · finalizada · ${new Date(corrida.inicio).toLocaleString('es-EC').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')} · 3 incidencias$`))
  expect(line.textContent).not.toMatch(/\.\.$/)
  for (const text of ['peticiones', 'fichas observadas', 'candidatos nuevos', 'borradores creados', 'Motivo']) expect(line).not.toHaveTextContent(text)
  expect(screen.queryByText(/Última corrida programada/)).not.toBeInTheDocument()
  cleanup()
  // Con 0 incidencias se omite el fragmento.
  vi.mocked(offersApi.get).mockResolvedValue({ ...ready, ultima_ejecucion: { id: 13, estado: 'fallida', inicio: corrida.inicio },
    ultima_programada: { ...corrida, ejecucion_id: 13, estado: 'fallida', incidencias_total: 0 } })
  open()
  const sinIncidencias = (await screen.findByText(/Última corrida:/)).closest('p')
  expect(sinIncidencias).toHaveTextContent(/#13 · fallida · /)
  expect(sinIncidencias).not.toHaveTextContent('incidencia')
  cleanup()
  vi.mocked(offersApi.get).mockResolvedValue({ ...ready, ultima_ejecucion: null, ultima_programada: null })
  open()
  expect(await screen.findByText('Última corrida: sin ejecuciones')).toBeVisible()
})
