import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider'
import ProfileLayout from './components/ProfileLayout'
import { useAuth } from './auth/context'
import { authApi, ApiError } from './api/client'

function Consumer() { const { user } = useAuth(); return user ? <ProfileLayout><h1>Hola, {user.nombre}</h1></ProfileLayout> : null }
const account = { id: 77, nombre: 'Nombre anterior', email: 'nombre@example.com', rol: 'administrador' }
beforeEach(() => {
  vi.spyOn(authApi, 'me').mockResolvedValue(account)
  // jsdom no implementa el diálogo nativo; el comportamiento de foco/modal
  // se comprueba además en Edge con Playwright.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false } })
})
afterEach(() => { vi.restoreAllMocks(); delete HTMLDialogElement.prototype.showModal; delete HTMLDialogElement.prototype.close })
async function mount() {
  render(<MemoryRouter><AuthProvider><Consumer /></AuthProvider></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: 'Editar nombre' }))
  return within(screen.getByRole('dialog'))
}
it.each(['administrador'])('actualiza contexto y navegación de %s sin recargar', async rol => {
  vi.mocked(authApi.me).mockResolvedValue({ ...account, rol })
  const save = vi.spyOn(authApi, 'updateName').mockResolvedValue({ nombre: 'María <b>José</b>' })
  const form = await mount()
  expect(form.getByLabelText('Nombre visible')).toHaveValue(account.nombre)
  await userEvent.clear(form.getByLabelText('Nombre visible'))
  await userEvent.type(form.getByLabelText('Nombre visible'), 'María <b>José</b>')
  await userEvent.click(form.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith('María <b>José</b>')
  expect(await screen.findByRole('heading', { name: 'Hola, María <b>José</b>' })).toBeVisible()
  expect(screen.getByText('María <b>José</b>', { selector: 'span' })).toBeVisible()
  expect(document.querySelector('b')).toBeNull()
  expect(screen.getByText('Nombre actualizado.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Editar nombre' })).toHaveFocus()
})
it('cancelar conserva el nombre y no llama a la API', async () => {
  const save = vi.spyOn(authApi, 'updateName')
  const form = await mount()
  await userEvent.type(form.getByLabelText('Nombre visible'), ' cambio')
  await userEvent.click(form.getByRole('button', { name: 'Cancelar' }))
  expect(save).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'Hola, Nombre anterior' })).toBeVisible()
})
it('error conserva contexto y entrada; permite corregir y reintentar', async () => {
  const save = vi.spyOn(authApi, 'updateName').mockRejectedValueOnce(new ApiError('Revisa el nombre', 400, { nombre: ['Nombre inválido de prueba'] })).mockResolvedValue({ nombre: 'Nuevo' })
  const form = await mount()
  await userEvent.clear(form.getByLabelText('Nombre visible'))
  await userEvent.type(form.getByLabelText('Nombre visible'), 'Nuevo')
  await userEvent.click(form.getByRole('button', { name: 'Guardar' }))
  expect(await form.findByRole('alert')).toHaveTextContent('Nombre inválido de prueba')
  expect(screen.getByRole('heading', { name: 'Hola, Nombre anterior' })).toBeInTheDocument()
  expect(form.getByLabelText('Nombre visible')).toHaveValue('Nuevo')
  await userEvent.click(form.getByRole('button', { name: 'Guardar' }))
  expect(await screen.findByText('Nombre actualizado.')).toBeVisible()
  expect(save).toHaveBeenCalledTimes(2)
})
it('bloquea doble envío mientras guarda', async () => {
  let resolve
  const save = vi.spyOn(authApi, 'updateName').mockImplementation(() => new Promise(r => { resolve = r }))
  const form = await mount()
  await userEvent.dblClick(form.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledTimes(1)
  expect(form.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
  resolve({ nombre: account.nombre })
  expect(await screen.findByText('Nombre actualizado.')).toBeVisible()
})

