import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import AuthProvider from './auth/AuthProvider'

const GENERIC = 'Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la contraseña.'
const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
})
let fetchMock
let responder
function mount(path) {
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
}
const bodyOf = (path) => JSON.parse(fetchMock.mock.calls.find(([url]) => url.endsWith(path))[1].body)

beforeEach(() => {
  responder = {}
  fetchMock = vi.fn(async (url) => {
    if (url.endsWith('/me/')) return json({ detail: 'Sin sesión' }, 403)
    if (url.endsWith('/csrf/')) return json({ csrfToken: 'csrf-prueba' })
    for (const [path, reply] of Object.entries(responder)) if (url.endsWith(path)) return reply()
    throw new Error('Solicitud no simulada en la prueba')
  })
  vi.stubGlobal('fetch', fetchMock)
})

describe('Recuperación de contraseña', () => {
  it('el inicio de sesión enlaza a la recuperación', async () => {
    mount('/login')
    const link = await screen.findByRole('link', { name: '¿Olvidaste tu contraseña?' })
    expect(link).toHaveAttribute('href', '/recuperar-contrasena')
    await userEvent.click(link)
    expect(await screen.findByRole('heading', { name: 'Recupera tu contraseña' })).toBeVisible()
  })

  it('solicitud: valida el correo y muestra siempre el mensaje genérico', async () => {
    responder['/recuperar-contrasena/'] = () => json({ detail: GENERIC })
    mount('/recuperar-contrasena')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Enviar enlace' }))
    expect(screen.getByText('Ingresa tu correo electrónico.')).toBeVisible()
    expect(screen.getByLabelText('Correo electrónico')).toHaveFocus()
    await user.type(screen.getByLabelText('Correo electrónico'), ' persona@example.com ')
    await user.click(screen.getByRole('button', { name: 'Enviar enlace' }))
    expect(await screen.findByText(`${GENERIC} Revisa también la carpeta de correo no deseado.`)).toBeVisible()
    expect(bodyOf('/recuperar-contrasena/')).toEqual({ email: 'persona@example.com' })
    expect(screen.queryByRole('form', { name: 'Recuperar contraseña' })).not.toBeInTheDocument()
  })

  it('solicitud: muestra el límite de intentos sin revelar nada del correo', async () => {
    responder['/recuperar-contrasena/'] = () => json({ detail: 'Request was throttled.' }, 429, { 'Retry-After': '60' })
    mount('/recuperar-contrasena')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Correo electrónico'), 'persona@example.com')
    await user.click(screen.getByRole('button', { name: 'Enviar enlace' }))
    expect(await screen.findByText('Has realizado demasiados intentos. Espera 60 segundos y vuelve a intentarlo.')).toBeVisible()
  })

  it('restablecimiento: envía uid y token del enlace y vuelve al inicio de sesión con un aviso', async () => {
    responder['/restablecer-contrasena/'] = () => json({ detail: 'Tu contraseña se actualizó. Ya puedes iniciar sesión.' })
    mount('/restablecer-contrasena#uid=MTI&token=abc-123')
    const user = userEvent.setup()
    expect(await screen.findByRole('heading', { name: 'Crea una contraseña nueva' })).toBeVisible()
    expect(screen.getByText(/Usa al menos 8 caracteres/)).toBeVisible()  // requisitos visibles
    await user.type(screen.getByLabelText('Contraseña nueva'), 'Clave-Nueva!5821')
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Otra-Distinta!1')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    expect(screen.getByText('Las contraseñas no coinciden.')).toBeVisible()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/restablecer-contrasena/'))).toBe(false)
    await user.clear(screen.getByLabelText('Confirmar contraseña'))
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Clave-Nueva!5821')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
    expect(screen.getByText('Tu contraseña se actualizó. Ya puedes iniciar sesión.')).toBeVisible()
    expect(bodyOf('/restablecer-contrasena/')).toEqual({ uid: 'MTI', token: 'abc-123', password: 'Clave-Nueva!5821', password_confirm: 'Clave-Nueva!5821' })
  })

  it('restablecimiento: contraseña débil muestra el motivo del servidor', async () => {
    responder['/restablecer-contrasena/'] = () => json({ password: ['Esta contraseña es demasiado común.'] }, 400)
    mount('/restablecer-contrasena#uid=MTI&token=abc-123')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Contraseña nueva'), 'password123')
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    expect(await screen.findByText('Esta contraseña es demasiado común.')).toBeVisible()
    expect(screen.getByLabelText('Contraseña nueva')).toHaveAttribute('aria-invalid', 'true')
  })

  it('enlace vencido o incompleto: lo explica y ofrece solicitar otro', async () => {
    responder['/restablecer-contrasena/'] = () => json({ detail: 'El enlace no es válido o ya venció. Solicita uno nuevo.', codigo: 'enlace_invalido' }, 400)
    mount('/restablecer-contrasena#uid=MTI&token=vencido')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Contraseña nueva'), 'Clave-Nueva!5821')
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'Clave-Nueva!5821')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))
    expect(await screen.findByRole('heading', { name: 'Enlace no válido' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Solicitar un enlace nuevo' })).toHaveAttribute('href', '/recuperar-contrasena')
  })

  it('sin uid ni token muestra directamente el enlace no válido', async () => {
    mount('/restablecer-contrasena')
    expect(await screen.findByRole('heading', { name: 'Enlace no válido' })).toBeVisible()
    await waitFor(() => expect(fetchMock.mock.calls.every(([url]) => !url.endsWith('/restablecer-contrasena/'))).toBe(true))
  })
})
