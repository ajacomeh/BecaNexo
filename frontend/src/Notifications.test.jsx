import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import Notifications from './pages/Notifications'
import ProfileLayout from './components/ProfileLayout'
import { offersApi } from './api/client'

vi.mock('./api/client', () => ({ offersApi: { get: vi.fn(), write: vi.fn() } }))
vi.mock('./components/OffersLayout', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Postulante', rol: 'postulante' }, logout: vi.fn() }) }))

const item = { id: 7, convocatoria_id: 42, titulo: 'Beca sintética', motivos: ['área de estudio declarada'],
  creada_en: '2026-11-07T14:00:00Z', leida_en: null, disponible: true }
const data = (results, extras = {}) => ({ count: results.length, no_leidas: results.filter((x) => !x.leida_en).length,
  page: 1, page_size: 10, results, ...extras })

function mount() {
  return render(<MemoryRouter initialEntries={['/notificaciones']}><Routes>
    <Route path="/notificaciones" element={<Notifications />} />
    <Route path="/becas/:id" element={<h1>Detalle de beca</h1>} />
  </Routes></MemoryRouter>)
}

beforeEach(() => vi.clearAllMocks())

it('mantiene el correo desactivado hasta consentimiento explícito y permite revocarlo', async () => {
  offersApi.get.mockImplementation((path) => Promise.resolve(path === 'notificaciones/correo'
    ? { disponible: true, habilitado: false } : data([])))
  offersApi.write.mockResolvedValueOnce({ disponible: true, habilitado: true })
    .mockResolvedValueOnce({ disponible: true, habilitado: false })
  mount()
  const checkbox = await screen.findByRole('checkbox', { name: 'Recibir avisos por correo' })
  expect(checkbox).not.toBeChecked()
  await userEvent.click(checkbox)
  await waitFor(() => expect(checkbox).toBeChecked())
  expect(offersApi.write).toHaveBeenCalledWith('notificaciones/correo', 'PATCH', { habilitado: true })
  await userEvent.click(checkbox)
  await waitFor(() => expect(checkbox).not.toBeChecked())
  expect(offersApi.write).toHaveBeenCalledWith('notificaciones/correo', 'PATCH', { habilitado: false })
})

it('recupera la preferencia guardada al volver a cargar la página', async () => {
  let saved = false
  offersApi.get.mockImplementation((path) => Promise.resolve(path === 'notificaciones/correo'
    ? { disponible: true, habilitado: saved } : data([])))
  offersApi.write.mockImplementation((_path, _method, body) => {
    saved = body.habilitado
    return Promise.resolve({ disponible: true, habilitado: saved })
  })
  const first = mount()
  let checkbox = await screen.findByRole('checkbox', { name: 'Recibir avisos por correo' })
  await userEvent.click(checkbox)
  await waitFor(() => expect(checkbox).toBeChecked())
  first.unmount()
  const second = mount()
  checkbox = await screen.findByRole('checkbox', { name: 'Recibir avisos por correo' })
  await waitFor(() => expect(checkbox).toBeChecked())
  await userEvent.click(checkbox)
  await waitFor(() => expect(checkbox).not.toBeChecked())
  second.unmount()
  mount()
  checkbox = await screen.findByRole('checkbox', { name: 'Recibir avisos por correo' })
  await waitFor(() => expect(checkbox).not.toBeChecked())
})

it('presenta carga, estado vacío, error y reintento', async () => {
  offersApi.get.mockRejectedValueOnce(new Error('Sin conexión')).mockResolvedValueOnce(data([]))
  mount()
  expect(screen.getByRole('status')).toHaveTextContent('Cargando notificaciones')
  expect(await screen.findByRole('alert')).toHaveTextContent('Sin conexión')
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByRole('heading', { name: 'Aún no tienes notificaciones' })).toBeVisible()
})

it('muestra la relación, navega al detalle y marca como leída sin perder el aviso ante error', async () => {
  offersApi.get.mockResolvedValue(data([item]))
  offersApi.write.mockRejectedValueOnce(new Error('No se pudo guardar')).mockResolvedValueOnce({ id: 7, leida_en: '2026-11-07T15:00:00Z' })
  mount()
  expect(await screen.findByText('Beca sintética')).toBeVisible()
  expect(screen.getByText(/La coincidencia no confirma todos los requisitos/)).toBeVisible()
  const notification = screen.getByText('Beca sintética').closest('li')
  expect(notification).toHaveTextContent('Sin leer')
  expect(notification).toHaveTextContent('Recibida:')
  expect(notification).toHaveTextContent('área de estudio declarada')
  expect(notification).toHaveTextContent('Ver beca')
  expect(notification.children[0]).toHaveClass('notification-content')
  expect(notification.children[1]).toHaveClass('notification-actions')
  await userEvent.click(screen.getByRole('button', { name: 'Marcar como leída' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo guardar')
  expect(screen.getByText('Sin leer')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Marcar como leída' }))
  await waitFor(() => expect(screen.getByText('Leída')).toBeVisible())
  expect(notification).not.toHaveTextContent('Marcar como leída')
  expect(screen.getByText('0 sin leer · 1 en total')).toBeVisible()
  expect(offersApi.write).toHaveBeenCalledWith('notificaciones/7/leer', 'POST', {})
  await userEvent.click(screen.getByRole('link', { name: 'Ver beca' }))
  expect(screen.getByRole('heading', { name: 'Detalle de beca' })).toBeVisible()
})

it('no crea enlace falso para convocatoria pausada y pagina resultados', async () => {
  const first = Array.from({ length: 10 }, (_, n) => ({ ...item, id: n + 1, titulo: `Aviso ${n + 1}` }))
  offersApi.get.mockImplementation((path, params) => Promise.resolve(path === 'notificaciones/correo'
    ? { disponible: false, habilitado: false } : params.page === 2
    ? data([{ ...item, id: 11, titulo: 'Último aviso', disponible: false }], { page: 2, count: 11, no_leidas: 11 })
    : data(first, { count: 11, no_leidas: 11 })))
  mount()
  expect(await screen.findByText('Aviso 1')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(await screen.findByText('Último aviso')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  expect(screen.queryByRole('link', { name: 'Ver beca' })).not.toBeInTheDocument()
  expect(screen.getByText('La convocatoria ya no está disponible públicamente.')).toBeVisible()
})

it('actualiza el indicador de no leídas en la navegación del postulante', async () => {
  offersApi.get.mockResolvedValueOnce({ no_leidas: 2 }).mockResolvedValueOnce({ no_leidas: 1 })
  render(<MemoryRouter><ProfileLayout><p>Contenido</p></ProfileLayout></MemoryRouter>)
  expect(await screen.findByRole('link', { name: 'Notificaciones, 2 sin leer' })).toBeVisible()
  window.dispatchEvent(new Event('becanexo:notificaciones'))
  expect(await screen.findByRole('link', { name: 'Notificaciones, 1 sin leer' })).toBeVisible()
})
