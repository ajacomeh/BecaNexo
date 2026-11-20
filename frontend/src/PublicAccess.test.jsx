import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from './App'
import AuthProvider from './auth/AuthProvider'
import { authApi, offersApi, ApiError } from './api/client'
import { safeReturnPath, loginReturnPath } from './auth/returnPath'

const user = { id: 1, nombre: 'Postulante de prueba', rol: 'postulante', email: 'test@example.com' }
const offer = { id: 12, titulo: 'Oferta pública de prueba', institucion: { nombre: 'Entidad de prueba' }, estado: 'sin_fecha', descripcion: 'Descripción', url_oficial: 'https://example.org/beca', opciones: [], beneficios: [], requisitos: [], favorito_id: null }
const catalogs = { paises: [], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }
function Path() { const location = useLocation(); return <output data-testid="path">{location.pathname}{location.search}</output> }
function mount(path) { render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /><Path /></AuthProvider></MemoryRouter>) }
beforeEach(() => {
  vi.spyOn(authApi, 'me').mockRejectedValue(new ApiError('Sin sesión', 403))
  vi.spyOn(authApi, 'login').mockResolvedValue(user)
  vi.spyOn(offersApi, 'write').mockResolvedValue({ id: 9 })
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : path === 'becas' ? { count: 1, page: 1, page_size: 12, results: [offer] } : offer)
})
afterEach(() => vi.restoreAllMocks())

it.each(['/becas', '/becas/12'])('consulta anónima %s y enlaces de cuenta', async (path) => {
  mount(path)
  expect(await screen.findByRole('heading', { name: offer.titulo })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Iniciar sesión' })).toHaveAttribute('href', '/login')
  expect(screen.getByRole('link', { name: 'Crear cuenta' })).toHaveAttribute('href', '/registro')
  expect(screen.queryByText('Gestionar convocatorias')).not.toBeInTheDocument()
  if (path.includes('12')) {
    expect(screen.getByRole('link', { name: 'Ver convocatoria oficial' })).toHaveAttribute('href', offer.url_oficial)
    expect(screen.getByText('La postulación se realiza fuera de BecaNexo. La entidad oferente confirma los documentos y adjudica la beca.')).toBeVisible()
  }
})

it('favorito anónimo, login y retorno al detalle sin guardado automático', async () => {
  mount('/becas')
  await userEvent.click(await screen.findByRole('link', { name: 'Guardar en favoritos' }))
  expect(screen.getByTestId('path')).toHaveTextContent('/login?next=%2Fbecas%2F12')
  await userEvent.type(screen.getByLabelText('Correo electrónico'), user.email)
  await userEvent.type(screen.getByLabelText('Contraseña'), 'Solo-para-test-74!')
  await userEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
  expect(await screen.findByRole('heading', { name: offer.titulo })).toBeVisible()
  expect(screen.getByTestId('path')).toHaveTextContent('/becas/12')
  expect(offersApi.write).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Guardar en favoritos' }))
  expect(offersApi.write).toHaveBeenCalledWith('favoritos', 'POST', { convocatoria: 12 })
})

it.each(['https://evil.example', '//evil.example', '/\\evil.example', 'javascript:alert(1)', '/gestion/convocatorias', '/perfil', '/becas/12?next=https://evil.example', '/becas/12#x', '/becas/12\n', '/becas/../gestion', '%2F%2Fevil.example', '/becas/0'])('rechaza retorno %s', (value) => {
  expect(safeReturnPath(value)).toBe('/inicio')
  expect(loginReturnPath(`?next=${encodeURIComponent(value)}`)).toBe('/inicio')
})
it('solo acepta catálogo y detalles, rechaza next repetido', () => {
  expect(safeReturnPath('/becas')).toBe('/becas')
  expect(safeReturnPath('/becas/12')).toBe('/becas/12')
  expect(loginReturnPath('?next=/becas&next=/becas/12')).toBe('/inicio')
})
it('sesión existente retorna al detalle sin login ni mutación', async () => {
  authApi.me.mockResolvedValue(user)
  mount('/login?next=%2Fbecas%2F12')
  expect(await screen.findByRole('heading', { name: offer.titulo })).toBeVisible()
  expect(authApi.login).not.toHaveBeenCalled()
  expect(offersApi.write).not.toHaveBeenCalled()
})
it.each(['postulante', 'administrador'])('retorno externo cae en inicio y respeta rol %s', async (rol) => {
  authApi.me.mockResolvedValue({ ...user, rol })
  mount('/login?next=https%3A%2F%2Fevil.example')
  expect(await screen.findByRole('heading', { name: `Hola, ${user.nombre}` })).toBeVisible()
  expect(screen.getByTestId('path')).toHaveTextContent('/inicio')
  const modules = within(screen.getByRole('navigation', { name: 'Accesos de Inicio' }))
  expect(Boolean(modules.queryByRole('link', { name: 'Convocatorias', exact: true }))).toBe(rol === 'administrador')
  if (rol === 'administrador') expect(modules.getByRole('link', { name: 'Convocatorias', exact: true })).toHaveAttribute('href', '/gestion/convocatorias')
})
it.each(['/perfil', '/preferencias', '/favoritos'])('mantiene protegida %s', async (path) => {
  mount(path)
  expect(await screen.findByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
})
