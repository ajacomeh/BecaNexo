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
const publication = { id: 1, titulo: 'Publicación sintética', fuente: { id: 1, nombre: 'SIAU prueba' }, url_original: 'https://example.org/ficha', primera_deteccion: '2026-11-01T10:00:00Z', ultima_deteccion: '2026-11-02T10:00:00Z', version_observada_id: 1 }
const candidate = { id: 24, titulo: 'Enlace de prueba', fuente: 'SIAU prueba', url: 'https://siau.senescyt.gob.ec/beca/', pagina: 3, primera_deteccion: '2026-11-15T10:00:00Z', ultima_deteccion: '2026-11-16T10:00:00Z', ejecucion_id: 10, estado: 'pendiente' }
function open(path = '/gestion/rastreo') { render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }

it('muestra los candidatos pendientes con total, procedencia y paginación', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path, params) => path.endsWith('/candidatos-indice')
    ? list([{ ...candidate, id: params.page === 2 ? 23 : 24 }], 24) : list())
  open('/gestion/rastreo/candidatos-indice')
  expect(await screen.findByRole('heading', { name: 'Candidatos del índice', level: 2 })).toBeVisible()
  expect(screen.getByText(/Todavía no constituyen convocatorias verificadas ni publicadas/)).toBeVisible()
  expect(screen.getByText('Página 1 de 2 · 24 registros')).toBeVisible()
  expect(screen.getByText('Enlace de prueba')).toBeVisible()
  expect(screen.getByRole('link', { name: candidate.url })).toHaveAttribute('href', candidate.url)
  expect(screen.getByRole('link', { name: 'Ejecución 10' })).toHaveAttribute('href', '/gestion/rastreo/ejecuciones/10')
  expect(document.querySelector('.crawl-candidate')).toHaveTextContent('Página de origen3')
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(get).toHaveBeenCalledWith('gestion/rastreo/candidatos-indice', { page: 2 })
})

it('permite reintentar una consulta de candidatos fallida', async () => {
  let attempts = 0
  vi.spyOn(offersApi, 'get').mockImplementation(async path => {
    if (!path.endsWith('/candidatos-indice')) return list()
    if (++attempts === 1) throw new Error('Consulta temporalmente no disponible')
    return list([candidate])
  })
  open('/gestion/rastreo/candidatos-indice')
  expect(await screen.findByText('Consulta temporalmente no disponible')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('Enlace de prueba')).toBeVisible()
})

it('separa descubrimiento de metadatos y muestra candidatos asociados en la ejecución', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path) => {
    if (path.endsWith('/ejecuciones/10')) return { id: 10, fuente: { nombre: 'SIAU' }, estado: 'parcial', tipo: 'metadatos_indice', candidatos_registrados: 12, accesos: 0, documentos_distintos: 0, publicaciones_observadas: 0, versiones_nuevas: 0, observaciones_sin_cambios: 0 }
    if (path.endsWith('/candidatos-indice')) return list([candidate], 12)
    return list()
  })
  open('/gestion/rastreo/ejecuciones/10')
  expect(await screen.findByText(/Descubrimiento de metadatos/)).toBeVisible()
  expect(screen.getByText('SIAU · Estado: parcial')).toBeVisible()
  expect(screen.getByText('Candidatos registrados').nextSibling).toHaveTextContent('12')
  expect(screen.getByText('Métricas documentales de esta ejecución')).toBeVisible()
  await userEvent.click(screen.getByText('Métricas documentales de esta ejecución'))
  expect(screen.getByText('Publicaciones observadas').nextSibling).toHaveTextContent('0')
  expect(await screen.findByRole('heading', { name: 'Candidatos registrados en esta ejecución' })).toBeVisible()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/candidatos-indice', { ejecucion: '10', page: 1 })
  expect(screen.getByRole('link', { name: candidate.url })).toHaveAttribute('href', candidate.url)
})

it('presenta las ejecuciones 9 y 10 como descubrimientos parciales con doce candidatos cada una', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(list([9, 10].map(id => ({
    id, fuente: { nombre: 'SIAU' }, estado: 'parcial', tipo: 'metadatos_indice',
    candidatos_registrados: 12, accesos: 0, documentos_distintos: 0,
    publicaciones_observadas: 0, versiones_nuevas: 0, observaciones_sin_cambios: 0,
  }))))
  open('/gestion/rastreo/ejecuciones')
  await screen.findByRole('link', { name: 'Ejecución 9' })
  expect(screen.getAllByText('SIAU · Estado: parcial')).toHaveLength(2)
  expect(screen.getAllByText('Candidatos registrados')).toHaveLength(2)
  expect(screen.getAllByText('12')).toHaveLength(2)
})

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
  expect(screen.getByRole('heading', { name: 'Rastreo', level: 2 })).toBeVisible()
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

it('identifica fuente, estado, última ejecución y borradores en el panel', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('/control')
    ? { puede_iniciar: false, fuentes_activas: 1, publicaciones_total: 3, borradores_total: 1,
      ultima_ejecucion: { id: 8, fuente: 'SIAU prueba', inicio: '2026-11-12T10:00:00Z', estado: 'parcial' },
      fuentes_registradas: [{ id: 1, nombre: 'SIAU prueba', activa: true, utilizable: true, politica_version: 'siau-nacionales/3', frecuencia_min: 1440 }],
      fuentes_configuracion: [{ id: 1, nombre: 'SIAU prueba', politica_version: 'siau-nacionales/3', frecuencia_min: 1440 }] }
    : list())
  open()
  expect((await screen.findByText('Publicaciones detectadas', { selector: 'dt' })).nextSibling).toHaveTextContent('3')
  expect(screen.getByText('Borradores automáticos').nextSibling).toHaveTextContent('1')
  // La última corrida se resume en una línea: número, estado y fecha (la fuente figura en «Fuentes registradas»).
  const run = screen.getByText(/Última corrida:/).closest('p')
  expect(run).toHaveTextContent(/^Última corrida: #8 · parcial · /)
  expect(run).toBeVisible()
  expect(screen.queryByText(/siau-nacionales\/3/)).not.toBeVisible()
  await userEvent.click(screen.getByText('Configuración y detalles técnicos'))
  expect(screen.getByText(/siau-nacionales\/3/)).toBeVisible()
})

it('muestra en la bandeja el borrador o el motivo claro de descarte, sin confianza', async () => {
  const draft = { ...publication, situacion: { tipo: 'borrador', convocatoria_id: 22, motivo: null } }
  const discarded = { ...publication, id: 2, titulo: 'Beca extranjera', situacion: { tipo: 'descartada', convocatoria_id: null,
    motivo: 'Descartada: oferente extranjero (Universidad extranjera), sin entidad ecuatoriana.' } }
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('/fuentes') ? list([{ id: 1, nombre: 'SIAU prueba' }]) : list([draft, discarded]))
  open()
  expect(await screen.findByText('Borrador privado', { selector: '.status-pill' })).toBeVisible()
  expect(screen.getByText(/Borrador privado #22/)).toBeVisible()
  expect(screen.queryByText(/onfianza/)).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Abrir borrador' })).toHaveAttribute('href', '/gestion/convocatorias/22')
  expect(screen.getByText('Descartada', { selector: '.status-pill' })).toBeVisible()
  expect(screen.getByText('Descartada: oferente extranjero (Universidad extranjera), sin entidad ecuatoriana.')).toBeVisible()
})

it('limpia los filtros de publicaciones y mantiene el acceso al detalle', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('/fuentes') ? list([{ id: 1, nombre: 'SIAU prueba' }]) : list([publication]))
  open()
  expect(await screen.findByRole('link', { name: 'Abrir publicación' })).toHaveAttribute('href', '/gestion/rastreo/publicaciones/1')
  expect(document.querySelectorAll('.crawl-publication-dates dt')).toHaveLength(2)
  expect(screen.getByText('No es una convocatoria aprobada del catálogo.')).toBeVisible()
  await userEvent.type(screen.getByLabelText('Buscar título o URL'), 'beca')
  await userEvent.selectOptions(screen.getByLabelText('Fuente'), '1')
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones', { q: 'beca', fuente: '1', page: 1 })
  await userEvent.click(screen.getByRole('button', { name: 'Limpiar' }))
  expect(screen.getByLabelText('Buscar título o URL')).toHaveValue('')
  expect(screen.getByLabelText('Fuente')).toHaveValue('')
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones', { page: 1 })
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
  expect(screen.getByRole('heading', { name: 'Publicación sintética' }).closest('.crawl-detail-hero')).toHaveTextContent('Una publicación detectada no equivale a una beca aprobada del catálogo.')
  expect(screen.getByRole('link', { name: publication.url_original })).toHaveAttribute('href', publication.url_original)
  expect(document.querySelectorAll('.crawl-detail-facts dt')).toHaveLength(6)
  await screen.findByText('Versión seleccionada')
  expect(document.querySelector('.crawl-version-current')).toHaveTextContent('Versión 1')
  expect(document.querySelector('img')).toBeNull()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/1', {})
  await userEvent.click(screen.getByRole('button', { name: 'Consultar versión 2' }))
  expect((await screen.findAllByText('Versión B'))[0]).toBeVisible()
  expect(screen.getByRole('heading', {name: 'Información extraída · versión 2'})).toHaveFocus()
  expect(document.querySelector('.crawl-version-current')).toHaveTextContent('Versión 2')
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/2/documentos', { page: 1 })
})

it('centraliza la revisión en Convocatorias y explica publicaciones sin borrador', async () => {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => {
    if (path.endsWith('publicaciones/1')) return { ...publication, convocatoria_id: 9,
      cierre_extraido: { texto_original: '12 de noviembre de 2026' },
      clasificacion_borrador: { estado: 'apta', motivo: 'Ficha individual verificada.' },
      borrador: { id: 9, revision: 'pendiente', activa: true, bloqueos: ['Confirmar nacionalidad'], observaciones: ['Revisar bases ZIP'] } }
    if (path.endsWith('/versiones/1')) return { numero: 1, datos_extraidos: { requisitos: { texto_original: 'Ser ecuatoriano' } }, texto_extraido: 'Texto íntegro', advertencias: [] }
    return list()
  })
  open('/gestion/rastreo/publicaciones/1')
  expect(await screen.findByRole('link', { name: 'Abrir borrador en Convocatorias' })).toHaveAttribute('href', '/gestion/convocatorias/9')
  expect(screen.getByText('Confirmar nacionalidad')).toBeVisible()
  expect(screen.getByText('12 de noviembre de 2026')).toBeVisible()
  expect((await screen.findAllByText('Ser ecuatoriano'))[0]).toBeVisible()
  expect(screen.getByText('Evidencias y versiones')).toBeVisible()
  expect(screen.queryByText('Revisiones administrativas')).not.toBeInTheDocument()
  expect(screen.queryByText('Propuesta de integración')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Registrar revisión' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Continuar propuesta' })).not.toBeInTheDocument()
  expect(get.mock.calls.some(([path]) => path.includes('/propuestas') || path.includes('/revisiones'))).toBe(false)
})

it('explica por qué no existe borrador sin ofrecer una propuesta manual', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path.endsWith('publicaciones/1')
    ? { ...publication, version_observada_id: null, clasificacion_borrador: { estado: 'pendiente', motivo: 'Falta comprobar requisitos.' } }
    : list())
  open('/gestion/rastreo/publicaciones/1')
  expect(await screen.findByText(/Falta comprobar requisitos/)).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Abrir borrador en Convocatorias' })).not.toBeInTheDocument()
  expect(screen.getByText('No hay una versión conservada para esta publicación.')).toBeVisible()
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
  await userEvent.click(await screen.findByText('Documentos asociados'))
  await userEvent.click(await screen.findByRole('button', { name: 'Descargar evidencia' }))
  expect(screen.getByText('Evidencia 4 · ficha html').closest('.crawl-document')).toHaveTextContent('text/html')
  expect(screen.getByText('Evidencia 4 · ficha html').closest('.crawl-document')).toHaveTextContent('Documento conservado')
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
  ['publicaciones/1/versiones', '/gestion/rastreo/publicaciones/1', 'Seleccionar versión'],
  ['publicaciones/1/observaciones', '/gestion/rastreo/publicaciones/1', 'Historial'],
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
  await screen.findByRole('heading', {name: 'Información extraída · versión 1'})
  await screen.findByText('Versión seleccionada')
  expect(screen.queryByRole('button', {name: 'Consultar versión 1'})).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', {name: 'Consultar versión 2'}))
  expect(await screen.findByText('Versión temporalmente no disponible')).toBeVisible()
  expect(screen.queryByRole('heading', {name: 'Información extraída · versión 1'})).not.toBeInTheDocument()
  failure = false
  await userEvent.click(screen.getByRole('button', {name: 'Reintentar'}))
  expect(await screen.findByRole('heading', {name: 'Información extraída · versión 2'})).toHaveFocus()
  await userEvent.click(screen.getByText('Estudios y contextos mencionados'))
  const group = screen.getByText('Estudios y contextos mencionados').closest('details')
  expect(within(group).getAllByText('Contexto compartido')).toHaveLength(1)
  expect(within(group).getByText('maestría · especialización')).toBeVisible()
  expect(get).toHaveBeenCalledWith('gestion/rastreo/publicaciones/1/versiones/22/documentos', {page: 1})
})
