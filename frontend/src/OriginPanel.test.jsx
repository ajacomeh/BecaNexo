import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import OriginPanel from './components/OriginPanel'
import { offersApi } from './api/client'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const origin = { aplicacion: { propuesta_id: 3 }, publicacion_id: 4, version_id: 5,
  observacion_base_id: 6, version_convocatoria: 1, hash_convocatoria: 'a'.repeat(64),
  estado: { bloqueos: [], pendientes: [{ id: 'SIN_OPCIONES:opciones', codigo: 'SIN_OPCIONES',
    campo: 'opciones', motivo: 'Falta una opción confirmada' }] }, resoluciones: [] }

const automatic = { aplicacion: null, automatico: true, publicacion_id: 15, version_id: 23, version_convocatoria: 3,
  enlaces_origen: { publicacion: 'https://siau.example/ficha', bases: [{ url: 'https://siau.example/bases.pdf' }, { url: 'javascript:alert(1)' }],
    postulacion: [{ url: 'https://siau.example/postula' }] },
  para_publicar: ['Asigna una institución oferente ecuatoriana antes de publicar.', 'Añade al menos una opción activa.'],
  evidencia: { campos: [{ campo: 'url_oficial', valor: 'https://siau.example/ficha', literal: 'Enlace de postulación de la ficha', documento_id: 47, seccion: 'Enlaces de la ficha' }],
    registros: [{ modelo: 'requisitos', id: 5, texto: 'No haber sido sancionada con la prohibición de postular.', documento_id: 47, seccion: 'Requisitos' },
      { modelo: 'beneficios', id: 6, texto: 'Subvención de USD 569.23 para manutención.', documento_id: 47, seccion: 'Beneficio' },
      { modelo: 'opciones', id: 7, texto: 'maestria · virtual · Ecuador', documento_id: 47, seccion: 'Estudios', pagina: 2 }] } }

it('presenta el origen del borrador de forma compacta, con enlaces y lo que falta para publicar', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(automatic)
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 3 }} /></MemoryRouter>)
  expect(await screen.findByText('Borrador generado por rastreo')).toBeVisible()
  expect(screen.getByText(/Publicación 15 · Versión 23\. Ninguna beca se publica automáticamente\./)).toBeVisible()
  expect(screen.getByRole('link', { name: /Consultar ficha/ })).toHaveAttribute('href', '/gestion/rastreo/publicaciones/15')
  expect(screen.getByRole('link', { name: 'Abrir ficha de origen' })).toHaveAttribute('href', 'https://siau.example/ficha')
  expect(screen.getByRole('link', { name: 'Bases 1' })).toHaveAttribute('href', 'https://siau.example/bases.pdf')
  expect(screen.queryByRole('link', { name: 'Bases 2' })).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Para publicar falta' })).toBeVisible()
  expect(screen.getByText('Asigna una institución oferente ecuatoriana antes de publicar.')).toBeVisible()
  expect(screen.getByText('Añade al menos una opción activa.')).toBeVisible()
  for (const removed of [/Requisitos extraídos/, /Beneficios interpretados/, /Opciones sugeridas/, /Tablas y anexos/,
    /Bases PDF archivadas/, /Propuestas documentales/, /Datos complementarios/, /Datos de origen conservados/, /Precargar propuestas/, /onfianza/]) {
    expect(screen.queryByText(removed)).not.toBeInTheDocument()
  }
  expect(screen.queryByRole('button', { name: /Preparar en editor|Precargar|Aceptar|Descartar/ })).not.toBeInTheDocument()
})

it('ofrece un único desplegable cerrado con el texto literal y el documento y página de cada registro', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue(automatic)
  const write = vi.spyOn(offersApi, 'write')
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 3 }} /></MemoryRouter>)
  const summary = await screen.findByText('Ver evidencia de origen')
  expect(document.querySelectorAll('.crawl-origin details')).toHaveLength(1)
  expect(summary.closest('details')).not.toHaveAttribute('open')
  await userEvent.setup().click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  expect(screen.getByText('Enlace de postulación de la ficha')).toBeVisible()
  expect(screen.getByText(/No haber sido sancionada con la prohibición de postular\./)).toBeVisible()
  expect(screen.getByText(/Subvención de USD 569\.23 para manutención\./)).toBeVisible()
  expect(screen.getByText('Documento 47 · Sección: Requisitos')).toBeVisible()
  expect(screen.getByText('Documento 47 · Sección: Estudios · Página 2')).toBeVisible()
  expect(write).not.toHaveBeenCalled()
})

it('indica que no falta nada cuando no quedan pendientes y no muestra evidencia si no hay registros', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ ...automatic, para_publicar: [], evidencia: { campos: [], registros: [] } })
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 3 }} /></MemoryRouter>)
  expect(await screen.findByText(/No falta nada\./)).toBeVisible()
  expect(screen.queryByText('Ver evidencia de origen')).not.toBeInTheDocument()
})

it('conserva la justificación y la evidencia ante un error y permite reintentar', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 1, results: [{ evidencia_id: 8, rol: 'bases_pdf' }] } : origin)
  const write = vi.spyOn(offersApi, 'write').mockRejectedValueOnce(new Error('Conflicto de versión'))
    .mockResolvedValueOnce({ id: 11 })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1 }} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Pendiente'), 'SIN_OPCIONES:opciones')
  await user.selectOptions(screen.getByLabelText('Evidencia documental revisada'), '8')
  await user.type(screen.getByLabelText('Justificación y comprobación'), 'Opción cotejada con bases')
  await user.click(screen.getByRole('button', { name: 'Registrar resolución' }))
  expect(await screen.findByText(/Conflicto de versión/)).toBeVisible()
  expect(screen.getByLabelText('Justificación y comprobación')).toHaveValue('Opción cotejada con bases')
  expect(screen.getByLabelText('Evidencia documental revisada')).toHaveValue('8')
  await user.click(screen.getByRole('button', { name: 'Registrar resolución' }))
  expect(await screen.findByText(/Resolución registrada/)).toBeVisible()
  expect(write).toHaveBeenCalledTimes(2)
})

it('no presenta procedencia en una convocatoria manual', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ aplicacion: null })
  render(<MemoryRouter><OriginPanel offer={{ id: 9, version: 1 }} /></MemoryRouter>)
  await waitFor(() => expect(screen.queryByText('Consultando origen…')).not.toBeInTheDocument())
  expect(screen.queryByText('Registrar resolución comprobada')).not.toBeInTheDocument()
})

it('avisa de una versión relevante y confirma su revisión sin aplicar datos automáticamente', async () => {
  const current = { ...automatic, version_actual_id: 24, cambio_relevante: true, revision_confirmada: false,
    para_publicar: ['Confirmar versión 24'] }
  vi.spyOn(offersApi, 'get').mockResolvedValue(current)
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({})
  render(<MemoryRouter><OriginPanel offer={{ id: 11, version: 3 }} /></MemoryRouter>)
  expect(await screen.findByText(/versión 24 contiene cambios posteriores/)).toBeVisible()
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Motivo de revisión de la nueva versión'), 'Comparé la ficha y conservo el título editado.')
  await user.click(screen.getByRole('button', { name: 'Confirmar versión revisada' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/rastreo/convocatorias/11/origen', 'POST',
    { version_id: 24, version_convocatoria: 3, motivo: 'Comparé la ficha y conservo el título editado.' }))
})

it('muestra la correspondencia estable entre candidato y opción sin confundir alternativas iguales', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 0, results: [] } : { ...origin,
      aplicacion: { propuesta_id: 3, opciones_ids: { o1: 11, o2: 12 } },
      estado: { bloqueos: [], pendientes: [] },
      resoluciones: [{ id: 15, pendiente_id: 'opciones.o3', motivo: 'Revisión exacta',
        evidencia_id: 8, opcion_candidata_id: 'o3', opcion_estudio_id: 13 }] })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1,
    opciones: [{ id: 11, programa: 'Programa compartido' }, { id: 12, programa: 'Programa compartido' }] }} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(await screen.findByText('Correspondencias de opciones creadas'))
  expect(screen.getByText(/Candidato o1 → opción 11: Programa compartido/)).toBeVisible()
  expect(screen.getByText(/Candidato o2 → opción 12: Programa compartido/)).toBeVisible()
  await user.click(screen.getByText('Resoluciones registradas'))
  expect(screen.getByText(/Candidato o3 → opción 13/)).toBeVisible()
})

it('permite revisar cierre por día y tope, pero mantiene pendiente la apertura sin hora', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path.endsWith('/documentos')
    ? { count: 0, results: [] } : { ...origin, estado: { bloqueos: [], pendientes: [
      { id: 'fecha', codigo: 'PRECISION_TEMPORAL', campo: 'cierre_original', motivo: 'Hora desconocida' },
      { id: 'tope', codigo: 'TOPE_NO_REPRESENTADO', campo: 'beneficios.b1', motivo: 'Tope por revisar' },
      { id: 'apertura', codigo: 'PRECISION_TEMPORAL', campo: 'apertura_original', motivo: 'Apertura sin hora' },
    ] } })
  render(<MemoryRouter><OriginPanel offer={{ id: 7, version: 1 }} /></MemoryRouter>)
  const selector = await screen.findByLabelText('Pendiente')
  expect(selector.querySelector('option[value="fecha"]')).not.toBeDisabled()
  expect(selector.querySelector('option[value="tope"]')).not.toBeDisabled()
  expect(selector.querySelector('option[value="apertura"]')).toBeDisabled()
})
