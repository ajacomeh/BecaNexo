import { afterEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider'
import { authApi } from './api/client'
import App from './App'

afterEach(() => vi.restoreAllMocks())

it.each([
  ['postulante', [['Explorar becas', '/becas'], ['Mi perfil', '/perfil'], ['Idiomas y preferencias', '/preferencias'], ['Mis favoritas', '/favoritos']]],
  ['administrador', [['Convocatorias', '/gestion/convocatorias'], ['Entidades oferentes', '/gestion/instituciones'], ['Rastreo', '/gestion/rastreo']]],
])('integra Inicio de %s sin duplicar acciones de cuenta', async (rol, links) => {
  vi.spyOn(authApi, 'me').mockResolvedValue({ id: 99, nombre: 'María de prueba', rol })
  render(<MemoryRouter initialEntries={['/inicio']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  expect(await screen.findByRole('heading', { name: 'Hola, María de prueba' })).toBeVisible()
  const navigation = within(screen.getByRole('navigation', { name: 'Navegación principal' }))
  expect(navigation.getByRole('link', { name: 'Inicio', exact: true })).toHaveAttribute('aria-current', 'page')
  const cards = within(screen.getByRole('navigation', { name: 'Accesos de Inicio' }))
  expect(cards.getAllByRole('link')).toHaveLength(links.length)
  for (const [name, route] of links) {
    const link = cards.getByRole('link', { name, exact: true })
    expect(link).toHaveAttribute('href', route)
    expect(link).toHaveAccessibleDescription()
    expect(link.querySelector('button, a, input')).toBeNull()
  }
  expect(screen.getAllByRole('button', { name: 'Cerrar sesión' })).toHaveLength(1)
  expect(screen.getAllByRole('button', { name: 'Editar nombre' })).toHaveLength(1)
  expect(screen.getAllByRole('banner')).toHaveLength(1)
  expect(screen.getAllByRole('contentinfo')).toHaveLength(1)
  expect(screen.queryByText('Tu cuenta')).not.toBeInTheDocument()
  expect(screen.queryByText(/PANTALLA INICIAL DEL AVANCE|Avance inicial/)).not.toBeInTheDocument()
  expect(screen.getByText('Tu espacio en BecaNexo')).toBeVisible()
})
