import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import App from './App'

const auth = vi.hoisted(() => ({ status: 'authenticated', user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }))
vi.mock('./auth/context', () => ({ useAuth: () => auth }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.status = 'authenticated'; auth.user = { nombre: 'Admin sintético', rol: 'administrador' } })
const list = (results = [], count = results.length) => ({ results, count, page: 1, page_size: 12 })
const publication = { id: 1, titulo: 'Publicación sintética', fuente: { id: 1, nombre: 'SIAU prueba' }, url_original: 'https://example.org/ficha', version_observada_id: 1 }
function open(path = '/gestion/rastreo') { render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }

it('muestra carga, error, reintento y vacío sin acciones editoriales', async () => {
  let failed = false
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => {
    if (path.endsWith('/control')) return { politica_version: 'siau-indice/2', frecuencia_min: 1440, puede_iniciar: false }
    if (path.endsWith('/fuentes')) return list([{id: 1, nombre: 'SIAU prueba'}])
    if (!failed) { failed = true; throw new Error('Error simulado') }
    return list()
  })
  open()
  expect(screen.getAllByRole('status').some(node => node.textContent.includes('Cargando'))).toBe(true)
  expect(await screen.findByText('Error simulado')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('No hay registros para esta consulta.')).toBeVisible()
  expect(get).toHaveBeenCalledTimes(4)
  expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
  expect(screen.queryByRole('button', { name: /aprobar|publicar|ejecutar/i })).not.toBeInTheDocument()
})

it('envía búsqueda, fuente y paginación bajo los resultados', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('/fuentes') ? list([{id: 1, nombre: 'SIAU prueba'}]) : list([publication], 25))
  open()
  await screen.findByText('Publicación sintética')
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  await screen.findByText('Página 2 de 3 · 25 registros')
  expect(get).toHaveBeenLastCalledWith('gestion/rastreo/publicaciones', { page: 2 })
  await userEvent.type(screen.getByLabelText('Buscar título o URL'), 'beca')
  await userEvent.selectOptions(screen.getByLabelText('Fuente'), '1')
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
  await screen.findByText('Página 1 de 3 · 25 registros')
  expect(get).toHaveBeenLastCalledWith('gestion/rastreo/publicaciones', { q: 'beca', fuente: '1', page: 1 })
})

it('consulta la versión observada A aunque exista B y renderiza texto sin HTML', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path.endsWith('publicaciones/1')) return publication
    if (path.endsWith('/versiones')) return list([{ id: 2, numero: 2 }, { id: 1, numero: 1 }])
    if (path.endsWith('/versiones/1')) return { id: 1, numero: 1, datos_extraidos: { titulo: '<img src=x onerror=alert(1)>' }, advertencias: ['Pendiente de revisión'] }
    if (path.endsWith('/versiones/2')) return { id: 2, numero: 2, datos_extraidos: { titulo: 'Versión B' }, advertencias: [] }
    return list()
  })
  open('/gestion/rastreo/publicaciones/1')
  expect((await screen.findAllByText('<img src=x onerror=alert(1)>'))[0]).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/1', {})
  await userEvent.click(screen.getByRole('button', { name: 'Consultar versión 2' }))
  expect((await screen.findAllByText('Versión B'))[0]).toBeVisible()
  expect(screen.getByRole('heading', {name: 'Información de la versión 2'})).toHaveFocus()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/2/documentos', { page: 1 })
})

it('presenta el error de descarga sin éxito ficticio', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path.endsWith('publicaciones/1')) return publication
    if (path.endsWith('/versiones/1')) return { numero: 1, datos_extraidos: {}, advertencias: [] }
    if (path.endsWith('/documentos')) return list([{ id: 4, mime: 'text/html', rol: 'ficha_html', tamano_bytes: 10, sha256: 'a'.repeat(64) }])
    return list()
  })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: false, status: 409 })
  open('/gestion/rastreo/publicaciones/1')
  await userEvent.click(await screen.findByRole('button', { name: 'Descargar evidencia' }))
  expect(await screen.findByText('Evidencia no disponible o inconsistente.')).toBeVisible()
})

it('ejecución sin publicaciones conserva contadores y acceso a incidencias', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('ejecuciones/1') ? { id: 1, fuente: { nombre: 'SIAU' }, estado: 'finalizada', accesos: 6, documentos_distintos: 6, publicaciones_observadas: 0, versiones_nuevas: 0, observaciones_sin_cambios: 0 } : list())
  open('/gestion/rastreo/ejecuciones/1')
  expect(await screen.findByText('SIAU · Descarga finalizada')).toBeVisible()
  expect(screen.getByText('Publicaciones observadas').nextSibling).toHaveTextContent('0')
  expect(screen.getByRole('heading', { name: 'Incidencias' })).toBeVisible()
})

it('postulante no puede navegar a Rastreo ni ve su menú', async () => {
  auth.user = { nombre: 'Postulante sintético', rol: 'postulante' }
  const get = vi.spyOn(offersApi, 'get')
  open('/gestion/rastreo')
  expect(screen.queryByRole('heading', { name: 'Rastreo' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Rastreo' })).not.toBeInTheDocument()
  expect(get.mock.calls.some(([path]) => path.startsWith('gestion/rastreo'))).toBe(false)
})
import { within } from '@testing-library/react'
import Button from './components/Button'

it('busy conserva el bloqueo aunque disabled sea false', () => {
  const { rerender } = render(<Button busy disabled={false}>Guardar</Button>)
  expect(screen.getByRole('button')).toBeDisabled()
  expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true')
  rerender(<Button disabled>Guardar</Button>)
  expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'false')
})

it.each([
  ['publicaciones', '/gestion/rastreo', 'Publicaciones detectadas'],
  ['publicaciones/1/versiones', '/gestion/rastreo/publicaciones/1', 'Versiones registradas'],
  ['publicaciones/1/observaciones', '/gestion/rastreo/publicaciones/1', 'Historial de observaciones'],
  ['ejecuciones', '/gestion/rastreo/ejecuciones', 'Ejecuciones'],
  ['ejecuciones/1/accesos', '/gestion/rastreo/ejecuciones/1', 'Accesos'],
  ['ejecuciones/1/incidencias', '/gestion/rastreo/ejecuciones/1', 'Incidencias'],
])('pagina %s con solicitudes y contenido distintos, y respeta extremos', async (target, route, title) => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path, params) => {
    if (path === 'gestion/rastreo/publicaciones/1') return publication
    if (path === 'gestion/rastreo/ejecuciones/1') return {id: 1, fuente: {nombre: 'Prueba'}, estado: 'finalizada'}
    if (path.endsWith('/versiones/1')) return {numero: 1, datos_extraidos: {}}
    if (path === 'gestion/rastreo/' + target) {
      const page = params.page
      return {count: 2, page, page_size: 1, results: [{
        ...publication, id: page, numero: page, titulo: 'Fila ' + page,
        resultado: 'Resultado ' + page, rol: 'Acceso ' + page, codigo: 'Incidencia ' + page
      }]}
    }
    return list()
  })
  open(route)
  const section = (await screen.findByRole('heading', {name: title, level: 2})).closest('section')
  const scope = within(section)
  await scope.findByText('Página 1 de 2 · 2 registros')
  expect(scope.getByRole('button', {name: 'Anterior'})).toBeDisabled()
  const first = section.querySelector('li').textContent
  await userEvent.click(scope.getByRole('button', {name: 'Siguiente'}))
  await scope.findByText('Página 2 de 2 · 2 registros')
  expect(section.querySelector('li').textContent).not.toEqual(first)
  expect(get).toHaveBeenCalledWith('gestion/rastreo/' + target, {page: 2})
  expect(scope.getByRole('button', {name: 'Siguiente'})).toBeDisabled()
  await userEvent.click(scope.getByRole('button', {name: 'Anterior'}))
  await scope.findByText('Página 1 de 2 · 2 registros')
  expect(section.querySelector('li').textContent).toEqual(first)
})

it('muestra contador sin acciones para una sola página', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(list([publication]))
  open()
  await screen.findByText('1 registro')
  expect(screen.queryByRole('button', {name: 'Siguiente'})).not.toBeInTheDocument()
  expect(screen.queryByRole('button', {name: 'Anterior'})).not.toBeInTheDocument()
})
it('selecciona por ID global distinto del número, maneja error y agrupa contextos', async () => {
  let failure = true
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => {
    if (path.endsWith('publicaciones/1')) return {...publication, version_observada_id: 11}
    if (path.endsWith('/versiones')) return list([{id: 22, numero: 2}, {id: 11, numero: 1}])
    if (path.endsWith('/versiones/11')) return {numero: 1, datos_extraidos: {}}
    if (path.endsWith('/versiones/22')) {
      if (failure) throw new Error('Versión temporalmente no disponible')
      return {numero: 2, datos_extraidos: {estudios: {menciones_academicas: [
        {expresion_original: 'maestría', contexto_original: 'Contexto compartido', seccion: 'objetivo', funcion: 'oferta_mencionada'},
        {expresion_original: 'especialización', contexto_original: 'Contexto compartido', seccion: 'objetivo', funcion: 'oferta_mencionada'}
      ]}}}
    }
    return list()
  })
  open('/gestion/rastreo/publicaciones/1')
  await screen.findByRole('heading', {name: 'Información de la versión 1'})
  expect(screen.queryByRole('button', {name: 'Consultar versión 1'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', {name: 'Consultar versión 2'}))
  expect(await screen.findByText('Versión temporalmente no disponible')).toBeVisible()
  expect(screen.queryByRole('heading', {name: 'Información de la versión 1'})).not.toBeInTheDocument()
  failure = false
  await userEvent.click(screen.getByRole('button', {name: 'Reintentar'}))
  expect(await screen.findByRole('heading', {name: 'Información de la versión 2'})).toHaveFocus()
  await userEvent.click(screen.getByText('Estudios y contextos mencionados'))
  const group = screen.getByText('Estudios y contextos mencionados').closest('details')
  expect(within(group).getAllByText('Contexto compartido')).toHaveLength(1)
  expect(within(group).getByText('maestría · especialización')).toBeVisible()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/22/documentos', {page: 1})
})
