import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import AuthProvider from './auth/AuthProvider'
import { authApi, ApiError } from './api/client'

const title = 'Encuentra oportunidades para continuar tus estudios'
function mount(path = '/') { render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>) }
beforeEach(() => { vi.spyOn(authApi, 'me').mockRejectedValue(new ApiError('Sin sesión', 403)) })

it('presenta contenido público y enlaces funcionales sin requerir cuenta', async () => {
  mount()
  expect(await screen.findByRole('heading', { name: title })).toBeVisible()
  const nav = within(screen.getByRole('navigation', { name: 'Navegación principal' }))
  expect(nav.getByRole('link', { name: 'Explorar becas' })).toHaveAttribute('href', '/becas')
  expect(nav.getByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute('href', '/login')
  expect(nav.getByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro')
  expect(screen.getByRole('heading', { name: 'Cómo funciona' })).toBeVisible()
  expect(screen.getByRole('list').children).toHaveLength(4)
  expect(screen.getByText('La postulación y la adjudicación corresponden a las entidades oferentes. BecaNexo facilita la consulta de oportunidades.')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Mi panel' })).not.toBeInTheDocument()
})

it.each(['postulante', 'administrador'])('sesión %s reemplaza accesos de cuenta por panel', async (rol) => {
  authApi.me.mockResolvedValue({ id: 1, nombre: 'Persona de prueba', rol })
  mount()
  await screen.findByRole('heading', { name: title })
  expect(screen.queryByRole('link', { name: 'Iniciar sesión' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Crear cuenta' })).not.toBeInTheDocument()
  const links = screen.getAllByRole('link', { name: 'Mi panel' })
  links.forEach(link => expect(link).toHaveAttribute('href', '/inicio'))
  await userEvent.click(links[0])
  expect(await screen.findByRole('heading', { name: 'Hola, Persona de prueba' })).toBeVisible()
  expect(Boolean(screen.queryByRole('link', { name: 'Gestionar convocatorias' }))).toBe(rol === 'administrador')
})

it.each(['/login?next=%2Fbecas%2F12', '/registro'])('permite volver a la bienvenida desde %s', async (path) => {
  mount(path)
  await screen.findByRole('heading', { name: path.startsWith('/login') ? 'Inicia sesión' : 'Crea tu cuenta' })
  await userEvent.click(await screen.findByRole('link', { name: 'BecaNexo, volver al inicio' }))
  expect(await screen.findByRole('heading', { name: title })).toBeVisible()
})

it('inicio personal sigue protegido', async () => {
  mount('/inicio')
  expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
})
