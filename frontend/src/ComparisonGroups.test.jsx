import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Comparison from './components/Comparison'
import { AuthContext } from './auth/context'
import { offersApi } from './api/client'

const catalogs = { paises: [], idiomas: [], areas: [], tipos_requisito: [
  { codigo: 'NACIONALIDAD', nombre: 'Nacionalidad' }, { codigo: 'IDIOMA', nombre: 'Idioma' }, { codigo: 'EDAD', nombre: 'Edad' },
  { codigo: 'DEDICACION', nombre: 'Dedicación' }, { codigo: 'DOCUMENTO', nombre: 'Documento' },
] }
const req = (id, tipo, resultado, extra = {}) => ({ id, tipo, descripcion: `Condición ${id}`, obligatorio: true, ambito: 'comun', resultado,
  explicacion: `Explicación ${id}`, dato_declarado: null, condicion_exigida: { valores: {} }, comprobacion_externa: false, ...extra })
const requisitos = [
  req(1, 'NACIONALIDAD', 'cumple'),
  req(2, 'IDIOMA', 'desconocido', { seccion_perfil: 'idiomas' }),
  req(3, 'EDAD', 'no_cumple', { seccion_perfil: 'datos-personales' }),
  req(4, 'DOCUMENTO', 'desconocido', { comprobacion_externa: true, seccion_perfil: 'datos-personales' }),
  req(5, 'DEDICACION', 'no_cumple'),
  req(6, 'IDIOMA', 'cumple', { seccion_perfil: 'idiomas' }),
]
const option = { id: 1, programa: 'Programa agrupado', nivel: 'maestria', modalidad: 'virtual', destinos: ['Ecuador'], resultado: 'desconocido',
  resumen: 'Falta información para confirmar', requisitos, verificaciones_externas_pendientes: 1 }
const response = { aviso: 'La entidad oferente verifica los documentos.', criterio_destacada: 'Primera opción.', opcion_destacada_id: 1, opciones: [option] }

async function mount(data = response) {
  vi.spyOn(offersApi, 'get').mockResolvedValue(data)
  render(<MemoryRouter><AuthContext.Provider value={{ user: { id: 1, rol: 'postulante' } }}><Comparison offerId={12} catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  return (await screen.findByRole('heading', { name: 'Programa agrupado' })).closest('article')
}
beforeEach(() => { vi.restoreAllMocks() })

it('agrupa por resultado en el orden No cumples, Por confirmar y Cumplidos, con su conteo', async () => {
  const article = await mount()
  const groups = [...article.querySelectorAll('details.comparison-group')]
  expect(groups.map(group => group.querySelector('summary').textContent)).toEqual(['No cumples (2)', 'Por confirmar (2)', 'Cumplidos (2)'])
  expect(groups.map(group => group.className)).toEqual([
    'comparison-group comparison-group-no_cumple', 'comparison-group comparison-group-desconocido', 'comparison-group comparison-group-cumple'])
})

it('abre por defecto lo que no se cumple y lo pendiente, y deja plegados los cumplidos', async () => {
  const article = await mount()
  const [noCumple, pendiente, cumplidos] = article.querySelectorAll('details.comparison-group')
  expect(noCumple).toHaveAttribute('open')
  expect(pendiente).toHaveAttribute('open')
  expect(cumplidos).not.toHaveAttribute('open')
  // El desplegable nativo se abre al activar su resumen (teclado o puntero) y los lectores anuncian su estado.
  await userEvent.click(within(cumplidos).getByText('Cumplidos (2)'))
  expect(cumplidos).toHaveAttribute('open')
})

it('conserva el orden original de los requisitos dentro de cada grupo', async () => {
  const article = await mount()
  const [noCumple, pendiente, cumplidos] = article.querySelectorAll('details.comparison-group')
  const textos = group => [...group.querySelectorAll('li > p.preserve-text')].map(p => p.textContent)
  expect(textos(noCumple)).toEqual(['Condición 3', 'Condición 5'])
  expect(textos(pendiente)).toEqual(['Condición 2', 'Condición 4'])
  expect(textos(cumplidos)).toEqual(['Condición 1', 'Condición 6'])
})

it('no muestra un grupo vacío', async () => {
  const article = await mount({ ...response, opciones: [{ ...option, requisitos: [req(1, 'NACIONALIDAD', 'cumple'), req(2, 'IDIOMA', 'desconocido')] }] })
  expect([...article.querySelectorAll('details.comparison-group summary')].map(s => s.textContent)).toEqual(['Por confirmar (1)', 'Cumplidos (1)'])
  expect(within(article).queryByText(/^No cumples/)).not.toBeInTheDocument()
})

it('ofrece el botón de actualización solo en requisitos no cumplidos o por confirmar que dependen de un dato del postulante', async () => {
  const article = await mount()
  const [noCumple, pendiente, cumplidos] = article.querySelectorAll('details.comparison-group')
  expect(within(noCumple).getByRole('link', { name: 'Actualizar datos personales' })).toHaveAttribute('href', '/perfil#datos-personales')
  expect(within(noCumple).getAllByRole('link')).toHaveLength(1)
  // El idioma pendiente lleva su botón; el documento que verifica la entidad oferente conserva su mensaje y no lleva botón.
  expect(within(pendiente).getByRole('link', { name: 'Actualizar idiomas y niveles' })).toHaveAttribute('href', '/preferencias#idiomas')
  expect(within(pendiente).getAllByRole('link')).toHaveLength(1)
  expect(within(pendiente).getByText('Verificación externa pendiente')).toBeInTheDocument()
  expect(within(cumplidos).queryByRole('link')).not.toBeInTheDocument()
  // El resumen superior y sus acciones se mantienen.
  expect(screen.getByRole('region', { name: 'Resumen superior: Programa agrupado' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Actualizar perfil' })).toBeVisible()
})
