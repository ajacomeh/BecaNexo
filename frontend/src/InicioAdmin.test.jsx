import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider'
import { authApi, offersApi } from './api/client'
import App from './App'

afterEach(() => vi.restoreAllMocks())

async function inicio(rol) {
  vi.spyOn(authApi, 'me').mockResolvedValue({ id: 99, nombre: 'Persona sintética', rol })
  vi.spyOn(offersApi, 'get').mockResolvedValue({ results: [], count: 0, page_size: 12, no_leidas: 0 })
  render(<MemoryRouter initialEntries={['/inicio']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  await screen.findByRole('heading', { name: 'Hola, Persona sintética' })
}

it('el Inicio del administrador empieza por «Explorar becas», con el mismo orden e icono que la barra lateral', async () => {
  await inicio('administrador')
  const cards = within(screen.getByRole('navigation', { name: 'Accesos de Inicio' }))
  const titles = cards.getAllByRole('link').map(link => link.querySelector('h2').textContent)
  expect(titles).toEqual(['Explorar becas', 'Convocatorias', 'Entidades oferentes', 'Rastreo'])
  const explore = cards.getByRole('link', { name: 'Explorar becas' })
  expect(explore).toHaveAttribute('href', '/becas')
  expect(explore).toHaveAccessibleDescription('Consulta el catálogo público como lo ven los postulantes.')
  // Mismo orden de módulos que la barra lateral (sin Inicio).
  const sidebar = within(screen.getByRole('navigation', { name: 'Navegación principal' }))
  expect(sidebar.getAllByRole('link').map(link => link.textContent).slice(1)).toEqual(titles)
  // Mismo icono que «Explorar becas» en la barra lateral.
  const sidebarIcon = sidebar.getByRole('link', { name: 'Explorar becas' }).querySelector('svg').getAttribute('class')
  expect(explore.querySelector('svg').getAttribute('class')).toBe(sidebarIcon)
})

it('el Inicio del postulante no cambia', async () => {
  await inicio('postulante')
  const cards = within(screen.getByRole('navigation', { name: 'Accesos de Inicio' }))
  expect(cards.getAllByRole('link').map(link => [link.querySelector('h2').textContent, link.getAttribute('href')])).toEqual([
    ['Explorar becas', '/becas'], ['Mi perfil', '/perfil'], ['Idiomas y preferencias', '/preferencias'], ['Mis favoritas', '/favoritos'], ['Notificaciones', '/notificaciones']])
  expect(cards.getByRole('link', { name: 'Explorar becas' })).toHaveAccessibleDescription('Consulta oportunidades y sus requisitos.')
})

it('el bloque de usuario muestra el rol como etiqueta, conserva el botón de editar y «Cerrar sesión», y no tiene avatar', async () => {
  await inicio('administrador')
  const account = document.querySelector('.sidebar-account')
  const role = within(account).getByText('Administrador')
  expect(role).toHaveClass('sidebar-role')
  expect(within(account).getByText('Persona sintética', { selector: '.sidebar-name span' })).toBeVisible()
  // Sin avatar ni iniciales: el único icono del bloque de usuario es el lápiz de editar.
  const user = account.querySelector('.sidebar-user')
  expect(user.querySelectorAll('svg')).toHaveLength(1)
  expect(within(user).queryByText(/^PS$/)).not.toBeInTheDocument()
  expect(account.querySelector('img, [class*="avatar"]')).toBeNull()
  const edit = within(account).getByRole('button', { name: 'Editar nombre' })
  expect(edit).toHaveClass('edit-name-link')  // control de 44 px; su diálogo lo cubre EditName.test.jsx
  // «Cerrar sesión» con el mismo texto, icono y clases de antes.
  const logout = within(account).getByRole('button', { name: 'Cerrar sesión' })
  expect(logout).toHaveClass('button', 'button-outline', { exact: true })
  expect(logout.textContent).toBe('Cerrar sesión')
  expect(logout.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
})

it('el postulante ve el mismo bloque: nombre, etiqueta de rol y «Cerrar sesión», sin botón de editar', async () => {
  await inicio('postulante')
  const account = document.querySelector('.sidebar-account')
  expect(within(account).getByText('Postulante')).toHaveClass('sidebar-role')
  expect(within(account).queryByRole('button', { name: 'Editar nombre' })).not.toBeInTheDocument()
  expect(within(account).getByRole('button', { name: 'Cerrar sesión' })).toHaveClass('button', 'button-outline', { exact: true })
})
