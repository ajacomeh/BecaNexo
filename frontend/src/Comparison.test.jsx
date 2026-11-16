import { beforeEach, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import Comparison from './components/Comparison'
import { AuthContext } from './auth/context'
import { offersApi, ApiError } from './api/client'

const catalogs = { paises: [], idiomas: [], areas: [], tipos_requisito: [
  { codigo: 'NACIONALIDAD', nombre: 'Nacionalidad' }, { codigo: 'IDIOMA', nombre: 'Idioma' },
  { codigo: 'DEDICACION', nombre: 'Dedicación' }, { codigo: 'ACREDITACION', nombre: 'Acreditación' },
] }
const item = { id: 1, tipo: 'IDIOMA', descripcion: 'Inglés B2', obligatorio: true, ambito: 'comun', resultado: 'cumple', explicacion: 'Coincide según tus datos declarados.', dato_declarado: { idioma: 'en', nivel: 'B2' }, condicion_exigida: { valores: { nivel_minimo: 'B2' } }, comprobacion_externa: false }
const option = { id: 1, programa: 'Programa de prueba', nivel: 'maestria', modalidad: 'virtual', destinos: ['Ecuador'], resultado: 'cumple', resumen: 'Coincide según tus datos declarados', requisitos: [item], verificaciones_externas_pendientes: 0 }
const response = { aviso: 'La entidad oferente verifica los documentos.', criterio_destacada: 'Primera coincidencia declarada, sin ranking.', opcion_destacada_id: 1, opciones: [option] }
function LocationProbe() { const location = useLocation(); return <span data-testid="current-route">{location.pathname}{location.hash}</span> }
function mount(user = { id: 1, rol: 'postulante' }) {
  render(<MemoryRouter><AuthContext.Provider value={{ user }}><Comparison offerId={12} catalogs={catalogs} /><LocationProbe /></AuthContext.Provider></MemoryRouter>)
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

it('explica la preferencia híbrida sin convertirla en elegibilidad', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, modalidad: 'hibrida',
    resultado: 'desconocido', preferencia_modalidad: 'no_coincide' }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText(/Híbrida · Ecuador/)).toBeVisible()
  expect(screen.getByText(/Preferencia de modalidad: no coincide/)).toBeVisible()
  expect(screen.getByText(/No determina elegibilidad/)).toBeVisible()
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
  expect(screen.queryByRole('region', { name: 'Resumen para Ecuador' })).not.toBeInTheDocument()
  expect(summary).toBeVisible()
  await userEvent.click(summary)
  expect(screen.getByRole('region', { name: 'Resumen para España' })).toBeVisible()
  expect(screen.getByText('Traslado presencial obligatorio')).toBeVisible()
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.queryByText(/identificador/)).not.toBeInTheDocument()
})

it('resume los tres estados antes del detalle y distingue el estado general', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'no_cumple', requisitos: [
    item,
    { ...item, id: 2, resultado: 'no_cumple', tipo: 'DEDICACION', descripcion: 'Dedicación completa' },
    { ...item, id: 3, resultado: 'desconocido', tipo: 'ACREDITACION', descripcion: 'Certificado externo', comprobacion_externa: true },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  const summary = await screen.findByRole('region', { name: 'Resumen superior: Programa de prueba' })
  expect(within(summary).getByText('Cumplidos').previousSibling).toHaveTextContent('1')
  expect(within(summary).getByText('Incumplidos').previousSibling).toHaveTextContent('1')
  expect(within(summary).getByText('Sin información suficiente').previousSibling).toHaveTextContent('1')
  expect(within(summary).getByRole('list', { name: 'Coincidencias declaradas' })).toHaveTextContent('Idioma')
  expect(within(summary).getByRole('list', { name: 'Incumplimientos declarados' })).toHaveTextContent('Dedicación')
  expect(within(summary).getByRole('list', { name: 'Información pendiente' })).toHaveTextContent('Acreditación')
  expect(summary).toHaveTextContent('requisito obligatorio que no coincide')
  expect(screen.getByRole('heading', { name: 'Incumplimientos declarados' })).toBeVisible()
  expect(summary.compareDocumentPosition(screen.getByText('Dedicación completa')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.queryByText(/probabilidad de adjudicación/i)).not.toBeInTheDocument()
})

it('ofrece rutas contextuales solo para datos actualizables y renueva al volver', async () => {
  const pending = { ...item, resultado: 'desconocido', explicacion: 'Falta nivel declarado.', seccion_perfil: 'idiomas' }
  offersApi.get.mockResolvedValueOnce({ ...response, opciones: [{ ...option, resultado: 'desconocido', requisitos: [pending] }] })
    .mockResolvedValueOnce(response)
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  const link = await screen.findByRole('link', { name: 'Actualizar idiomas y niveles' })
  expect(link).toHaveAttribute('href', '/preferencias#idiomas')
  expect(screen.getByRole('button', { name: 'Actualizar perfil' })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Actualizar preferencias' })).toBeVisible()
  fireEvent.focus(window)
  await screen.findByRole('region', { name: 'Resumen superior: Programa de prueba' })
  expect(await screen.findByText('Coincidencias declaradas')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Actualizar idiomas y niveles' })).not.toBeInTheDocument()
  expect(offersApi.get).toHaveBeenCalledTimes(2)
})

it('dirige los botones superiores a pantallas distintas y conserva el enlace específico de disponibilidad', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'no_cumple', requisitos: [
    { ...item, tipo: 'DEDICACION', resultado: 'no_cumple', seccion_perfil: 'disponibilidad' },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  await screen.findByRole('region', { name: 'Resumen superior: Programa de prueba' })
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar perfil' }))
  expect(screen.getByTestId('current-route')).toHaveTextContent('/perfil')
  expect(screen.getByRole('link', { name: 'Actualizar disponibilidad' })).toHaveAttribute('href', '/preferencias#disponibilidad')
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar preferencias' }))
  expect(screen.getByTestId('current-route')).toHaveTextContent('/preferencias#preferencias')
})

it('el botón de perfil enfoca formación cuando es la corrección pertinente', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'desconocido', requisitos: [
    { ...item, tipo: 'FORMACION', resultado: 'desconocido', seccion_perfil: 'formacion-academica' },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  await screen.findByRole('region', { name: 'Resumen superior: Programa de prueba' })
  await userEvent.click(screen.getByRole('button', { name: 'Actualizar perfil' }))
  expect(screen.getByTestId('current-route')).toHaveTextContent('/perfil#formacion-academica')
})

it('presenta disponibilidad completa como coincidencia con requisito parcial', async () => {
  const dedication = { ...item, tipo: 'DEDICACION', descripcion: 'Se exige tiempo parcial', resultado: 'cumple',
    dato_declarado: { dedicacion: 'completa' }, condicion_exigida: { valores: { valores_admitidos: ['parcial'] } } }
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, requisitos: [dedication] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  const summary = await screen.findByRole('region', { name: 'Resumen superior: Programa de prueba' })
  expect(within(summary).getByRole('list', { name: 'Coincidencias declaradas' })).toHaveTextContent('Dedicación')
  expect(within(summary).getByText('Incumplidos').previousSibling).toHaveTextContent('0')
  expect(screen.getByText('Se exige tiempo parcial')).toBeVisible()
  expect(screen.queryByRole('heading', { name: 'Opciones con incumplimientos obligatorios' })).not.toBeInTheDocument()
})

it('explica formaciones evaluadas sin exponer la clave interna del grupo académico', async () => {
  const academic = { ...item, tipo: 'FORMACION', descripcion: 'Se exige maestría finalizada', resultado: 'no_cumple',
    grupo_formacion: 'academico_D_0', dato_declarado: null,
    explicacion: 'Grupo academico_D_0: ninguna formación declarada satisface conjuntamente las condiciones; todas se descartan por al menos un dato conocido.',
    condicion_exigida: { valores: { estado_exigido: 'finalizada' } } }
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'no_cumple', requisitos: [academic] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText('Se exige maestría finalizada')).toBeVisible()
  expect(screen.getByText(/Se evaluaron tus formaciones declaradas; ninguna cumple conjuntamente/)).toBeVisible()
  expect(screen.getByText(/Condiciones de una misma formación: ninguna formación declarada/)).toBeVisible()
  expect(screen.getByText(/Estado de estudios exigido: finalizada/)).toBeVisible()
  expect(screen.queryByText(/academico_D_0/)).not.toBeInTheDocument()
  expect(screen.queryByText('Sin dato utilizado')).not.toBeInTheDocument()
})

it('distingue una condición pendiente sin datos suficientes de un incumplimiento académico', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'desconocido', requisitos: [
    { ...item, tipo: 'FORMACION', resultado: 'desconocido', dato_declarado: null, explicacion: 'No has declarado formaciones; no se interpreta como ausencia de estudios.' },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText(/No hay datos suficientes para confirmar esta condición/)).toBeVisible()
  expect(screen.getByText(/No has declarado formaciones/)).toBeVisible()
  expect(screen.queryByText(/Se evaluaron tus formaciones declaradas/)).not.toBeInTheDocument()
})

it('no sugiere editar el perfil para una acreditación externa o una regla sin revisión', async () => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'desconocido', requisitos: [
    { ...item, id: 2, tipo: 'ACREDITACION', resultado: 'desconocido', seccion_perfil: null, comprobacion_externa: true },
    { ...item, id: 3, tipo: 'EDAD', resultado: 'desconocido', seccion_perfil: null },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  await screen.findByRole('heading', { name: 'Programa de prueba' })
  expect(screen.queryByRole('link', { name: /Actualizar (datos|idiomas|disponibilidad)/ })).not.toBeInTheDocument()
})

it.each([
  ['NACIONALIDAD', 'datos-personales', 'Actualizar datos personales', '/perfil#datos-personales'],
  ['FORMACION', 'formacion-academica', 'Actualizar formación académica', '/perfil#formacion-academica'],
  ['EXPERIENCIA', 'experiencia', 'Actualizar experiencia', '/perfil#experiencia'],
  ['DEDICACION', 'disponibilidad', 'Actualizar disponibilidad', '/preferencias#disponibilidad'],
])('enlaza %s con su apartado editable', async (type, section, label, href) => {
  offersApi.get.mockResolvedValue({ ...response, opciones: [{ ...option, resultado: 'no_cumple', requisitos: [
    { ...item, tipo: type, resultado: 'no_cumple', seccion_perfil: section },
  ] }] })
  mount()
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByRole('link', { name: label })).toHaveAttribute('href', href)
})
