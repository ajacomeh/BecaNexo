import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import App from './App'

const auth = vi.hoisted(() => ({ status: 'authenticated', user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }))
vi.mock('./auth/context', () => ({ useAuth: () => auth }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const URL_LARGA = 'https://siau.senescyt.gob.ec/oferta-de-becas-nacionales-con-un-nombre-muy-largo-para-truncar/'
const execution = { id: 15, fuente: { nombre: 'SIAU' }, estado: 'finalizada', accesos: 60, documentos_distintos: 30, publicaciones_observadas: 12,
  versiones_nuevas: 0, observaciones_sin_cambios: 12, incidencias_error: 0, incidencias_aviso: 25 }
const access = (n) => ({ id: n, secuencia: n, rol: 'ficha', url_original: URL_LARGA + n, http_status: 200, resultado: 'reutilizado',
  documento_id: n, publicacion_id: n % 2 ? 7 : null, inicio_peticion_en: '2026-11-23T17:58:00Z', fin: '2026-11-23T17:58:01Z' })
const resumen = [{ codigo: 'BASE_NO_PERMITIDA', gravedad: 'aviso', total: 12 }, { codigo: 'CANDIDATO_PENDIENTE', gravedad: 'aviso', total: 8 },
  { codigo: 'CANDIDATO_FUERA_ALCANCE', gravedad: 'aviso', total: 4 }, { codigo: 'INDICE_LIMITE', gravedad: 'aviso', total: 1 }]

function mock({ accesses = 60, summary = resumen } = {}) {
  return vi.spyOn(offersApi, 'get').mockImplementation(async (path, params = {}) => {
    if (path === 'gestion/rastreo/ejecuciones/15') return execution
    if (path === 'gestion/rastreo/ejecuciones/15/accesos') {
      const first = (params.page - 1) * params.page_size
      return { count: accesses, page: params.page, page_size: params.page_size,
        results: Array.from({ length: Math.max(0, Math.min(params.page_size, accesses - first)) }, (_, i) => access(first + i + 1)) }
    }
    if (path === 'gestion/rastreo/ejecuciones/15/incidencias') {
      const total = summary.reduce((sum, g) => sum + g.total, 0)
      const count = params.codigo ? summary.find(g => g.codigo === params.codigo && g.gravedad === params.gravedad)?.total ?? 0 : total
      return { count, page: params.page, page_size: params.page_size, resumen: summary,
        results: Array.from({ length: Math.min(params.page_size, count) }, (_, i) => ({ id: i + 1, codigo: params.codigo || 'X', gravedad: params.gravedad || 'aviso',
          detectada_en: '2026-11-23T17:58:00Z', publicacion_id: i === 0 ? 9 : null, version_id: null })) }
    }
    return { results: [], count: 0, page: 1, page_size: 12 }
  })
}
// Buscar por rol y comparar el texto evita recalcular nombres accesibles de toda la App (lento en jsdom).
const tab = async (name) => (await screen.findAllByRole('tab', {}, { timeout: 3000 })).find(t => t.textContent === name)
const open = () => render(<MemoryRouter initialEntries={['/gestion/rastreo/ejecuciones/15']}><App /></MemoryRouter>)

it('muestra una sola lista a la vez con pestañas y contadores', async () => {
  mock()
  open()
  const accesos = await tab('Accesos (60)')
  const incidencias = await tab('Incidencias (25)')
  expect(accesos).toHaveAttribute('aria-selected', 'true')
  expect(incidencias).toHaveAttribute('aria-selected', 'false')
  expect(await screen.findByRole('table')).toBeVisible()
  expect(screen.queryByLabelText('Gravedad')).not.toBeInTheDocument()
  await userEvent.click(incidencias)
  expect(incidencias).toHaveAttribute('aria-selected', 'true')
  expect(await screen.findByLabelText('Gravedad')).toBeVisible()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', incidencias.id)
})

it('las pestañas se recorren con las flechas del teclado', async () => {
  mock()
  open()
  const accesos = await tab('Accesos (60)')
  accesos.focus()
  await userEvent.keyboard('{ArrowRight}')
  const incidencias = await tab('Incidencias (25)')
  expect(incidencias).toHaveFocus()
  expect(incidencias).toHaveAttribute('aria-selected', 'true')
  await userEvent.keyboard('{Home}')
  expect(accesos).toHaveAttribute('aria-selected', 'true')
})

it('accesos: filas compactas, 25 por página y paginador «1–25 de N»', async () => {
  const get = mock()
  open()
  const table = await screen.findByRole('table')
  expect(within(table).getAllByRole('columnheader').map(h => h.textContent)).toEqual(['Tipo', 'HTTP', 'Estado del documento', 'URL', 'Hora', 'Publicación'])
  expect(within(table).getAllByRole('row')).toHaveLength(26)
  expect(get).toHaveBeenCalledWith('gestion/rastreo/ejecuciones/15/accesos', { page: 1, page_size: 25 })
  const link = within(table).getByRole('link', { name: URL_LARGA + 1 })
  expect(link).toHaveAttribute('title', URL_LARGA + 1) // URL completa al pasar el cursor
  expect(link.closest('td')).toHaveClass('crawl-url')
  expect(within(table).getAllByRole('link', { name: '#7' })[0]).toHaveAttribute('href', '/gestion/rastreo/publicaciones/7')
  const pager = screen.getByRole('navigation', { name: 'Paginación de Accesos' })
  expect(within(pager).getByText('1–25 de 60')).toBeVisible()
  await userEvent.click(within(pager).getByRole('button', { name: 'Siguiente' }))
  expect(await screen.findByText('26–50 de 60')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(await screen.findByText('51–60 de 60')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
})

it('sin paginador cuando cabe en una página', async () => {
  mock({ accesses: 3 })
  open()
  await screen.findByRole('table')
  expect(screen.queryByRole('navigation', { name: 'Paginación de Accesos' })).not.toBeInTheDocument()
  expect(screen.getByText('3 registros')).toBeVisible()
})

it('incidencias agrupadas por tipo con contador, desplegables y filtro de gravedad', async () => {
  const get = mock({ summary: [{ codigo: 'RED', gravedad: 'error', total: 2 }, ...resumen] })
  open()
  await userEvent.click(await tab('Incidencias (25)'))
  const groups = await screen.findByRole('list', { name: 'Incidencias agrupadas por tipo' })
  const toggles = within(groups).getAllByRole('button')
  expect(toggles.map(b => b.textContent)).toEqual(['ErrorError de red×2', 'AvisoBases fuera de la lista cerrada×12',
    'AvisoCandidato pendiente de revisión×8', 'AvisoCandidato fuera de alcance×4', 'AvisoTope de fichas del índice×1'])
  const bases = toggles[1]
  expect(bases).toHaveAttribute('aria-expanded', 'false')
  await userEvent.click(bases)
  expect(bases).toHaveAttribute('aria-expanded', 'true')
  const detail = document.getElementById(bases.getAttribute('aria-controls'))
  expect(await within(detail).findByRole('link', { name: 'Publicación #9' })).toHaveAttribute('href', '/gestion/rastreo/publicaciones/9')
  expect(within(detail).getAllByRole('listitem')).toHaveLength(12)
  expect(get).toHaveBeenCalledWith('gestion/rastreo/ejecuciones/15/incidencias', { codigo: 'BASE_NO_PERMITIDA', gravedad: 'aviso', page: 1, page_size: 25 })
  const filter = screen.getByLabelText('Gravedad')
  expect([...filter.options].map(o => o.textContent)).toEqual(['Todas (27)', 'Error (2)', 'Aviso (25)'])
  await userEvent.selectOptions(filter, 'error')
  expect(within(groups).getAllByRole('button').map(b => b.textContent)).toEqual(['ErrorError de red×2'])
  await userEvent.selectOptions(filter, 'aviso')
  expect(within(screen.getByRole('list', { name: 'Incidencias agrupadas por tipo' })).getAllByRole('button')).toHaveLength(4)
})

it('sin incidencias muestra un mensaje en lugar de la lista', async () => {
  mock({ summary: [] })
  open()
  await userEvent.click(await screen.findByRole('tab', { name: /^Incidencias/ }))
  expect(await screen.findByText('No hay incidencias en esta ejecución.')).toBeVisible()
})

it('las incidencias editoriales muestran su motivo como texto plano; las técnicas quedan igual', async () => {
  const MOTIVO = 'Participación de ciudadanos ecuatorianos por confirmar en las bases. <b>https://example.org</b>'
  const summary = [{ codigo: 'RED', gravedad: 'error', total: 1 }, { codigo: 'BORRADOR_REVISION_PENDIENTE', gravedad: 'aviso', total: 2 }]
  vi.spyOn(offersApi, 'get').mockImplementation(async (path, params = {}) => {
    if (path === 'gestion/rastreo/ejecuciones/15') return { ...execution, incidencias_error: 1, incidencias_aviso: 2 }
    if (path !== 'gestion/rastreo/ejecuciones/15/incidencias') return { results: [], count: 0, page: 1, page_size: 12 }
    const base = { gravedad: params.gravedad, detectada_en: '2026-11-23T17:58:00Z', version_id: null }
    const results = params.codigo === 'BORRADOR_REVISION_PENDIENTE'
      ? [{ ...base, id: 1, codigo: params.codigo, publicacion_id: 27, detalle: MOTIVO }, { ...base, id: 2, codigo: params.codigo, publicacion_id: 28, detalle: '' }]
      : params.codigo === 'RED' ? [{ ...base, id: 3, codigo: 'RED', publicacion_id: null }] : []
    return { count: params.codigo ? results.length : 3, page: params.page, page_size: params.page_size, resumen: summary, results }
  })
  open()
  await userEvent.click(await tab('Incidencias (3)'))
  const groups = await screen.findByRole('list', { name: 'Incidencias agrupadas por tipo' })
  const [red, borrador] = within(groups).getAllByRole('button')
  expect(borrador).toHaveTextContent('AvisoBorrador con revisión pendiente×2') // el contador del grupo no cambia
  await userEvent.click(borrador)
  const detail = document.getElementById(borrador.getAttribute('aria-controls'))
  const motivo = await within(detail).findByText(MOTIVO)
  expect(motivo).toHaveClass('crawl-incident-reason')
  expect(motivo.querySelector('b, a')).toBeNull() // texto plano: ni HTML ni enlaces automáticos
  const filas = within(detail).getAllByRole('listitem')
  expect(filas).toHaveLength(2)
  expect(filas[1].querySelector('.crawl-incident-reason')).toBeNull() // sin detalle, la fila queda como siempre
  await userEvent.click(red)
  const tecnica = document.getElementById(red.getAttribute('aria-controls'))
  await within(tecnica).findByText('Sin publicación asociada')
  expect(tecnica.querySelector('.crawl-incident-reason')).toBeNull()
  // El filtro por gravedad sigue funcionando con los motivos visibles.
  await userEvent.selectOptions(screen.getByLabelText('Gravedad'), 'error')
  expect(within(screen.getByRole('list', { name: 'Incidencias agrupadas por tipo' })).getAllByRole('button').map(b => b.textContent)).toEqual(['ErrorError de red×1'])
  await userEvent.selectOptions(screen.getByLabelText('Gravedad'), 'aviso')
  expect(within(screen.getByRole('list', { name: 'Incidencias agrupadas por tipo' })).getAllByRole('button').map(b => b.textContent)).toEqual(['AvisoBorrador con revisión pendiente×2'])
})
