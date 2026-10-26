import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Comparison from './components/Comparison'
import { AuthContext } from './auth/context'
import { offersApi, ApiError } from './api/client'

const catalogs = { paises: [], idiomas: [], areas: [], tipos_requisito: [] }
const item = { id: 1, tipo: 'IDIOMA', descripcion: 'Inglés B2', obligatorio: true, ambito: 'comun', resultado: 'cumple', explicacion: 'Coincide según tus datos declarados.', dato_declarado: { idioma: 'en', nivel: 'B2' }, condicion_exigida: { valores: { nivel_minimo: 'B2' } }, comprobacion_externa: false }
const option = { id: 1, programa: 'Programa de prueba', nivel: 'maestria', modalidad: 'virtual', destinos: ['Ecuador'], resultado: 'cumple', resumen: 'Coincide según tus datos declarados', requisitos: [item], verificaciones_externas_pendientes: 0 }
const response = { aviso: 'La entidad oferente verifica los documentos.', criterio_destacada: 'Primera coincidencia declarada, sin ranking.', opcion_destacada_id: 1, opciones: [option] }
function mount(user = { id: 1, rol: 'postulante' }) {
  render(<MemoryRouter><AuthContext.Provider value={{ user }}><Comparison offerId={12} catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
}
beforeEach(() => { vi.spyOn(offersApi, 'get').mockResolvedValue(response) })

it('consulta solo al pulsar y presenta evidencia, condición y opción destacada', async () => {
  mount()
  expect(offersApi.get).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByRole('heading', { name: 'Programa de prueba' })).toBeVisible()
  expect(offersApi.get).toHaveBeenCalledWith('becas/12/comparacion')
  expect(screen.getByText('OPCIÓN DESTACADA PARA CONSULTA')).toBeVisible()
  expect(screen.getByText('Dato declarado utilizado')).toBeVisible()
  expect(screen.getByText('Condición exigida')).toBeVisible()
  expect(screen.queryByText(/%/)).not.toBeInTheDocument()
})

it('separa incompatibles, pendientes y acreditación externa aunque el idioma coincida', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [
    { ...option, verificaciones_externas_pendientes: 1, requisitos: [item, { ...item, id: 2, tipo: 'ACREDITACION', resultado: 'desconocido', descripcion: 'Certificado externo', comprobacion_externa: true }] },
    { ...option, id: 2, programa: 'Otra opción', resultado: 'no_cumple', resumen: 'No coincide con un requisito obligatorio', requisitos: [{ ...item, resultado: 'no_cumple' }] },
  ] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText('Verificación externa pendiente')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Información pendiente' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Coincidencias declaradas' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Incumplimientos declarados' })).toBeVisible()
  const separate = screen.getByRole('heading', { name: 'Opciones con incumplimientos obligatorios' }).parentElement
  expect(within(separate).getByRole('heading', { name: 'Otra opción' })).toBeVisible()
})

it('muestra carga, evita doble solicitud y permite reintentar error sin resultados falsos', async () => {
  let reject
  offersApi.get.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(screen.getByRole('status')).toHaveTextContent('Consultando')
  expect(screen.getByRole('button', { name: 'Comparando requisitos…' })).toBeDisabled()
  await act(async () => reject(new ApiError('Error de conexión')))
  expect(screen.getByRole('alert')).toHaveTextContent('Error de conexión')
  expect(screen.queryByRole('heading', { name: 'Programa de prueba' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar comparación' }))
  expect(await screen.findByRole('heading', { name: 'Programa de prueba' })).toBeVisible()
})

it('renueva al volver a la pestaña y elimina resultados si la oferta deja de estar disponible', async () => {
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  await screen.findByRole('heading', { name: 'Programa de prueba' })
  offersApi.get.mockRejectedValueOnce(new ApiError('Oculta', 404))
  fireEvent.focus(window)
  expect(await screen.findByRole('alert')).toHaveTextContent('ya no está disponible')
  expect(screen.queryByRole('heading', { name: 'Programa de prueba' })).not.toBeInTheDocument()
})

it('sin opciones muestra ausencia de información y no una coincidencia', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText('No hay opciones activas para comparar.')).toBeVisible()
  expect(screen.queryByText('Coincide según tus datos declarados')).not.toBeInTheDocument()
})

it('visitante tiene retorno seguro al detalle y no consulta comparación', () => {
  mount(null)
  expect(screen.getByRole('link', { name: 'Iniciar sesión para comparar requisitos' })).toHaveAttribute('href', '/login?next=%2Fbecas%2F12')
  expect(offersApi.get).not.toHaveBeenCalled()
})

it('administrador no tiene controles de comparación', () => {
  mount({ id: 2, rol: 'administrador' })
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
  expect(offersApi.get).not.toHaveBeenCalled()
})

it('muestra destinos con resultados diferentes sin ocultar el incompatible', async () => {
  offersApi.get.mockResolvedValue({ ...response, criterio_destacada: 'Se destaca una opción con coincidencias según tus datos declarados.', opciones: [{ ...option,
    resultados_destino: [{ pais: 'EC', nombre: 'Ecuador', resultado: 'cumple', resumen: 'Coincide según tus datos declarados', requisitos: [item] },
      { pais: 'ES', nombre: 'España', resultado: 'no_cumple', resumen: 'No coincide con un requisito obligatorio', requisitos: [{ ...item, descripcion: 'Traslado presencial obligatorio', resultado: 'no_cumple', ambito: 'destino' }] }],
  }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  const summary = await screen.findByText('España · No coincide con un requisito obligatorio')
  expect(summary).toBeVisible()
  await userEvent.click(summary)
  expect(screen.getByText('Traslado presencial obligatorio')).toBeVisible()
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.queryByText(/identificador/)).not.toBeInTheDocument()
})
