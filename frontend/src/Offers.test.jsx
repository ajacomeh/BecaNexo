import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import OfferForm from './components/OfferForm'
import { ApiError, offersApi } from './api/client'
import Offers from './pages/Offers'
import OfferEditor from './pages/OfferEditor'
import { RequirementList } from './pages/OfferDetail'
import { requirementFields, generalFields, benefitFields } from './pages/offerFields'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }
const filterCatalogs = { ...catalogs, niveles: [{ valor: 'maestria', nombre: 'Maestría' }], modalidades: [{ valor: 'virtual', nombre: 'Virtual' }], tipos_beca: [{ id: 3, nombre: 'Mérito' }] }
const adminListing = { count: 1, page: 1, page_size: 12, results: [{ id: 4, estado: 'borrador', titulo: 'Convocatoria sintética', institucion: { nombre: 'Entidad ficticia' }, beneficios: [], opciones: [], cierre: null }] }

describe('convocatorias', () => {
  it('muestra en cada borrador solo cuántos pasos faltan para publicar, sin confianza ni desplegable', async () => {
    const draft = { ...adminListing.results[0], revision: 'pendiente', origen_automatico: { publicacion_id: 3, version_id: 9 },
      diagnostico: { faltan: 2, pendientes_publicacion: ['Asigna una institución oferente ecuatoriana antes de publicar.', 'Añade al menos una opción activa.'] } }
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? filterCatalogs : { ...adminListing, results: [draft] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
    expect(await screen.findByText('Faltan 2 pasos para publicar')).toBeVisible()
    expect(screen.queryByText(/onfianza/)).not.toBeInTheDocument()
    expect(screen.queryByText('Qué falta revisar')).not.toBeInTheDocument()
    expect(screen.queryByText('Añade al menos una opción activa.')).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /onfianza/ })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByText('Más filtros'))
    expect(screen.queryByLabelText(/onfianza/)).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('gestion/convocatorias', {})
  })

  it('resume las opciones y muestra cierres con día o instante sin inventar horas', async () => {
    const makeOffer = (id, options, dates = {}) => ({
      id, titulo: `Convocatoria ${id}`, estado: id === 14 ? 'cerrada' : id === 16 ? 'borrador' : 'abierta',
      institucion: { nombre: 'Entidad ecuatoriana' }, beneficios: [], opciones: options, cierre: null, ...dates,
    })
    const udaOptions = [
      ...Array.from({ length: 4 }, (_, id) => ({ id, nivel: 'grado', modalidad: 'presencial', activa: true })),
      ...Array.from({ length: 3 }, (_, id) => ({ id: id + 4, nivel: 'grado', modalidad: 'hibrida', activa: true })),
    ]
    const offers = [
      ...[18, 19, 20].map(id => makeOffer(id, udaOptions, { cierre_dia: '2026-11-22' })),
      makeOffer(14, [{ nivel: 'grado', modalidad: 'hibrida', activa: true }], { cierre_dia: '2026-10-21' }),
      makeOffer(16, []),
      makeOffer(21, [{ nivel: 'grado', modalidad: 'presencial', activa: true },
        { nivel: 'maestria', modalidad: 'virtual', activa: true },
        { nivel: 'doctorado', modalidad: 'hibrida', activa: false }], { cierre: '2026-11-22T15:30:00Z' }),
    ]
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs :
      { count: offers.length, page: 1, page_size: 12, results: offers })
    render(<MemoryRouter><Offers admin /></MemoryRouter>)
    for (const id of [18, 19, 20]) {
      const card = (await screen.findByRole('heading', { name: `Convocatoria ${id}` })).closest('article')
      expect(within(card).getByText('Opciones de estudio: 7')).toBeVisible()
      expect(within(card).getByText('Nivel: Grado')).toBeVisible()
      expect(within(card).getByText('Modalidades: Presencial, Híbrida')).toBeVisible()
      expect(within(card).getByText(/Cierre: 22 nov 2026 · hora no informada/)).toBeVisible()
      expect(within(card).getByRole('link', { name: 'Editar y revisar' })).toHaveAttribute('href', `/gestion/convocatorias/${id}`)
    }
    const historic = screen.getByRole('heading', { name: 'Convocatoria 14' }).closest('article')
    expect(within(historic).getByText(/Cierre: 21 oct 2026/)).toBeVisible()
    const draft = screen.getByRole('heading', { name: 'Convocatoria 16' }).closest('article')
    expect(within(draft).getByText('Opciones de estudio: 0')).toBeVisible()
    expect(within(draft).getByText('Modalidades: No especificadas')).toBeVisible()
    expect(within(draft).getByText('Cierre: Fecha de cierre no informada')).toBeVisible()
    const mixed = screen.getByRole('heading', { name: 'Convocatoria 21' }).closest('article')
    expect(within(mixed).getByText('Opciones de estudio: 2')).toBeVisible()
    expect(within(mixed).getByText('Niveles: Grado, Maestría')).toBeVisible()
    expect(within(mixed).getByText('Modalidades: Presencial, Virtual')).toBeVisible()
    expect(within(mixed).getByText(/Cierre:.*10:30/)).toBeVisible()
  })

  it('identifica un borrador del rastreo sin oferente confirmado en administración', async () => {
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs :
      { count: 1, page: 1, page_size: 12, results: [{ id: 19, estado: 'borrador', titulo: 'Beca nacional sintética',
        institucion: null, origen_automatico: { publicacion_id: 8 }, beneficios: [], opciones: [], cierre: null }] })
    render(<MemoryRouter><Offers admin /></MemoryRouter>)
    expect(await screen.findByText('Oferente pendiente de confirmar')).toBeVisible()
    expect(screen.getByText(/Borrador del rastreo · Publicación 8/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Editar y revisar' })).toHaveAttribute('href', '/gestion/convocatorias/19')
  })
  it('aplica y limpia filtros administrativos, conserva los valores al contraer Más filtros y señala los activos', async () => {
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs : adminListing)
    render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
    const user = userEvent.setup()
    const form = await screen.findByRole('heading', { name: 'Filtros de búsqueda' })
    const filters = form.closest('section')
    expect(within(filters).getByText('Sin filtros activos')).toBeVisible()
    expect(within(filters).getByRole('option', { name: 'Todos los niveles' })).toBeInTheDocument()
    expect(within(filters).getByRole('option', { name: 'Todas las modalidades' })).toBeInTheDocument()
    expect(within(filters).getByRole('option', { name: 'Todos los destinos' })).toBeInTheDocument()
    expect(within(filters).queryByRole('option', { name: 'Sin declarar' })).not.toBeInTheDocument()
    await user.type(within(filters).getByLabelText('Buscar título, institución, área, descripción o programa'), 'Convocatoria')
    await user.selectOptions(within(filters).getByLabelText('Nivel'), 'maestria')
    const more = within(filters).getByText('Más filtros').closest('details')
    expect(more.open).toBe(false)
    await user.click(within(filters).getByText('Más filtros'))
    await user.selectOptions(within(filters).getByLabelText('Tipo de beca'), '3')
    await user.selectOptions(within(filters).getByLabelText('Estado'), 'borrador')
    await user.click(within(filters).getByText('Más filtros'))
    expect(more.open).toBe(false)
    await user.click(within(filters).getByText('Más filtros'))
    expect(within(filters).getByLabelText('Tipo de beca')).toHaveValue('3')
    expect(within(filters).getByLabelText('Estado')).toHaveValue('borrador')
    await user.click(within(filters).getByRole('button', { name: 'Aplicar filtros' }))
    await waitFor(() => expect(get).toHaveBeenCalledWith('gestion/convocatorias', expect.objectContaining({ q: 'Convocatoria', nivel: 'maestria', tipo_beca: '3', estado: 'borrador' })))
    expect(await screen.findByText('4 filtros activos')).toBeVisible()
    const previousRequests = get.mock.calls.filter(([path]) => path === 'gestion/convocatorias').length
    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await waitFor(() => expect(get.mock.calls.filter(([path]) => path === 'gestion/convocatorias')).toHaveLength(previousRequests + 1))
    expect(get.mock.calls.filter(([path]) => path === 'gestion/convocatorias').at(-1)[1]).toEqual({})
    expect(screen.getByText('Sin filtros activos')).toBeVisible()
    expect(screen.getByLabelText('Nivel')).toHaveValue('')
  })

  it('ordena resultados administrativos sin perder filtros y vuelve a la primera página', async () => {
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs : adminListing)
    render(<MemoryRouter initialEntries={['/gestion/convocatorias?nivel=maestria&page=2']}><Offers admin /></MemoryRouter>)
    const order = await screen.findByLabelText('Ordenar por')
    expect(screen.getByText('1 filtro activo')).toBeVisible()
    await userEvent.selectOptions(order, 'titulo')
    await waitFor(() => expect(get).toHaveBeenCalledWith('gestion/convocatorias', { nivel: 'maestria', orden: 'titulo' }))
    expect(screen.getByLabelText('Nivel')).toHaveValue('maestria')
    expect(screen.getByLabelText('Ordenar por')).toHaveValue('titulo')
  })

  it.each([0, 1])('oculta la paginación administrativa con %i convocatorias', async count => {
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs : { ...adminListing, count, results: count ? adminListing.results : [] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
    expect(await screen.findByText(`${count} convocatorias encontradas`)).toBeVisible()
    expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument()
  })

  it('pagina varias páginas y actualiza los controles al ordenar, filtrar y limpiar', async () => {
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path, params = {}) => path === 'becas/catalogos' ? filterCatalogs : {
      ...adminListing, count: params.estado ? 1 : 25, page: Number(params.page || 1),
    })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias?q=Oferta&page=2']}><Offers admin /></MemoryRouter>)
    const user = userEvent.setup()
    let pagination = await screen.findByRole('navigation', { name: 'Paginación' })
    expect(within(pagination).getByText('Página 2 de 3')).toBeVisible()
    expect(within(pagination).getByRole('button', { name: 'Anterior' })).toBeEnabled()
    expect(within(pagination).getByRole('button', { name: 'Siguiente' })).toBeEnabled()
    await user.click(within(pagination).getByRole('button', { name: 'Siguiente' }))
    pagination = await screen.findByRole('navigation', { name: 'Paginación' })
    expect(await within(pagination).findByText('Página 3 de 3')).toBeVisible()
    expect(within(pagination).getByRole('button', { name: 'Siguiente' })).toBeDisabled()
    await user.click(within(pagination).getByRole('button', { name: 'Anterior' }))
    expect(await screen.findByText('Página 2 de 3')).toBeVisible()
    await user.selectOptions(screen.getByLabelText('Ordenar por'), 'titulo')
    expect(await screen.findByText('Página 1 de 3')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    await waitFor(() => expect(get).toHaveBeenCalledWith('gestion/convocatorias', { q: 'Oferta', orden: 'titulo' }))
    await user.click(screen.getByText('Más filtros'))
    await user.selectOptions(screen.getByLabelText('Estado'), 'borrador')
    await user.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
    expect(await screen.findByText('1 convocatorias encontradas')).toBeVisible()
    expect(screen.queryByRole('navigation', { name: 'Paginación' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(await screen.findByText('Página 1 de 3')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  })

  it('envía día de cierre sin hora y conserva el literal de origen', async () => {
    const save = vi.fn().mockResolvedValue({})
    render(<OfferForm fields={generalFields(catalogs, [{ id: 1, nombre: 'Entidad ficticia' }])} onSubmit={save} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Título/), 'Oferta sintética')
    await user.selectOptions(screen.getByLabelText(/Entidad oferente ecuatoriana/), '1')
    await user.type(screen.getByLabelText('Día de cierre sin hora informada'), '2026-11-06')
    await user.type(screen.getByLabelText('Texto original del cierre'), '6 de noviembre de 2026')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ cierre: null, cierre_dia: '2026-11-06', cierre_original: '6 de noviembre de 2026' }))
  })

  it('envía un tope literal sin convertirlo en importe fijo ni asignar moneda', async () => {
    const save = vi.fn().mockResolvedValue({})
    render(<OfferForm fields={benefitFields([])} onSubmit={save} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/Concepto financiado/), 'Matrícula')
    await user.type(screen.getByLabelText('Tope literal según las bases'), '$3000')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ monto: null, moneda: null, tope_original: '$3000', tope_monto: null, tope_moneda: null }))
  })
  it('conserva entradas y presenta errores reales sin éxito ante rechazo', async () => {
    const save = vi.fn().mockRejectedValue(new ApiError('Revisa los datos.', 400, { titulo: ['Título inválido.'] }))
    render(<OfferForm fields={[{ name: 'titulo', label: 'Título' }]} onSubmit={save} />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Título'), 'Mi oferta')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Título inválido.')).toBeVisible()
    expect(screen.getByLabelText('Título')).toHaveValue('Mi oferta')
    expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
  })

  it('envía múltiples destinos y conserva cero y falso', async () => {
    const save = vi.fn().mockResolvedValue({})
    render(<OfferForm fields={[{ name: 'paises', label: 'Destinos', multiple: true, kind: 'ids', options: [{ value: 1, label: 'Ecuador' }, { value: 2, label: 'España' }] },
      { name: 'monto', label: 'Monto', kind: 'number' }, { name: 'activo', label: 'Activo', kind: 'boolean', options: [{ value: 'false', label: 'No' }] }]} onSubmit={save} />)
    const user = userEvent.setup()
    await user.click(screen.getByLabelText('Ecuador')); await user.click(screen.getByLabelText('España'))
    await user.type(screen.getByLabelText('Monto'), '0'); await user.selectOptions(screen.getByLabelText('Activo'), 'false')
    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(save).toHaveBeenCalledWith({ paises: [1, 2], monto: 0, activo: false })
  })

  it('bloquea doble envío mientras está guardando', async () => {
    let finish
    const save = vi.fn(() => new Promise((resolve) => { finish = resolve }))
    render(<OfferForm fields={[]} onSubmit={save} />)
    const user = userEvent.setup()
    await user.dblClick(screen.getByRole('button', { name: 'Guardar' }))
    expect(save).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
    finish({})
    expect(await screen.findByText('Cambios guardados.')).toBeVisible()
  })

  it('construye filtros en la URL correcta, sin alterar valores', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, status: 200, json: async () => ({ results: [] }) })
    await offersApi.get('becas', { nivel: 'maestria', destino: 'EC' })
    expect(fetch.mock.calls[0][0]).toBe('/api/becas/?nivel=maestria&destino=EC')
  })

  it('muestra catálogo vacío sin inventar ofertas', async () => {
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : { count: 0, page: 1, page_size: 12, results: [] })
    render(<MemoryRouter><Offers /></MemoryRouter>)
    expect(await screen.findByText('No hay becas de entidades ecuatorianas con estos filtros.')).toBeVisible()
    expect(screen.queryByText(/compatibilidad/i)).not.toBeInTheDocument()
  })

  it('el editor conserva campos cuando crear convocatoria falla', async () => {
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : { count: 1, results: [{ id: 1, nombre: 'DEMO institución' }] })
    vi.spyOn(offersApi, 'write').mockRejectedValue(new ApiError('Conflicto de datos.', 400))
    render(<MemoryRouter><OfferEditor /></MemoryRouter>)
    const title = await screen.findByLabelText(/Título/)
    expect(screen.getByText('Guarda el borrador antes de añadir opciones.')).toBeVisible()
    expect(within(screen.getByLabelText(/Entidad oferente ecuatoriana/).parentElement).getByRole('link', { name: 'Gestionar entidades oferentes' })).toHaveAttribute('href', '/gestion/instituciones')
    const user = userEvent.setup()
    await user.type(title, 'DEMO título conservado')
    await user.click(screen.getByRole('button', { name: 'Guardar convocatoria' }))
    expect(await screen.findByText('Conflicto de datos.')).toBeVisible()
    expect(title).toHaveValue('DEMO título conservado')
    expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
  })

  it('edita por ID dos opciones con nivel y modalidad iguales sin confundirlas', async () => {
    const options = [
      { id: 11, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa A', institucion_destino: 'Institución A', paises: [1], activa: true },
      { id: 12, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa B', institucion_destino: 'Institución B', paises: [1], activa: true },
    ]
    const offer = { id: 41, institucion: { id: 1 }, revision: 'pendiente', estado: 'borrador',
      opciones: options, beneficios: [], requisitos: [] }
    const get = vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs
      : path === 'gestion/convocatorias/41' ? offer : { count: 1, results: [{ id: 1, nombre: 'Entidad' }] })
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ ...options[1], programa: 'Programa B editado' })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
    const region = within(await screen.findByRole('region', { name: 'Opciones de estudio' }))
    expect(region.getByText(/Programa A · maestria \/ virtual · Institución A/)).toBeVisible()
    expect(region.getByText(/Programa B · maestria \/ virtual · Institución B/)).toBeVisible()
    await userEvent.click(region.getAllByRole('button', { name: 'Editar' })[1])
    expect(region.getByLabelText('Programa')).toHaveValue('Programa B')
    await userEvent.click(region.getByRole('button', { name: 'Guardar opciones de estudio' }))
    await waitFor(() => expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/opciones/12', 'PATCH', expect.objectContaining({ programa: 'Programa B' })))
    expect(get).toHaveBeenCalledWith('gestion/convocatorias/41')
  })

  it.each([
    ['borrador', 'pendiente', true],
    ['pausada', 'validada', false],
  ])('no ofrece pausar una convocatoria %s', async (estado, revision, activa) => {
    const offer = { id: 41, titulo: 'Convocatoria sintética', institucion: { id: 1, nombre: 'Entidad' },
      estado, revision, activa, version: 1, opciones: [], beneficios: [], requisitos: [] }
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs
      : path === 'gestion/convocatorias/41' ? offer : { count: 1, results: [{ id: 1, nombre: 'Entidad' }] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
    await screen.findByText(/Revisión:/)
    expect(screen.queryByRole('button', { name: 'Pausar convocatoria' })).not.toBeInTheDocument()
  })

  it('retira la acción de pausa tras pausar una convocatoria publicada', async () => {
    const offer = { id: 41, titulo: 'Convocatoria sintética', institucion: { id: 1, nombre: 'Entidad' },
      estado: 'abierta', revision: 'validada', activa: true, version: 1, opciones: [], beneficios: [], requisitos: [] }
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? filterCatalogs
      : path === 'gestion/convocatorias/41' ? offer : { count: 1, results: [{ id: 1, nombre: 'Entidad' }] })
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ ...offer, estado: 'pausada', activa: false, version: 2 })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Pausar convocatoria' }))
    expect(await screen.findByText('Convocatoria pausada.')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Pausar convocatoria' })).not.toBeInTheDocument()
    expect(write).toHaveBeenCalledTimes(1)
  })

  it('renderiza condiciones documentales como texto y verificación externa', () => {
    render(<RequirementList catalogs={catalogs} records={[{ id: 1, texto_original: '<script>alert(1)</script>', obligatorio: true, modo_comprobacion: 'entidad_oferente', valor_estructurado: {} }]} />)
    expect(screen.getByText('<script>alert(1)</script>')).toBeVisible()
    expect(screen.getByText(/BecaNexo no acredita/)).toBeVisible()
    expect(document.querySelector('script')).toBeNull()
  })

  it('edita el requisito elegido con texto extenso y conserva bloqueos y enlace en convocatoria guardada', async () => {
    const long = 'Descripción extensa con instrucciones completas. '.repeat(25) + 'https://example.org/' + 'a'.repeat(160)
    const offer = { id: 41, institucion: { id: 1 }, revision: 'pendiente', estado: 'borrador', opciones: [], beneficios: [], requisitos: [
      { id: 8, tipo_requisito: 1, texto_original: 'Primer requisito', activo: true, valor_estructurado: { documento: 'Primero' } },
      { id: 9, tipo_requisito: 1, texto_original: long, activo: true, valor_estructurado: { documento: 'Segundo' } },
    ] }
    const reference = { ...catalogs, tipos_requisito: [{ id: 1, codigo: 'DOCUMENTO', nombre: 'Documento externo', esquema_valor: { campos: { documento: { label: 'Nombre del documento', kind: 'text' } } } }] }
    vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? reference : path === 'gestion/convocatorias/41' ? offer : { count: 1, results: [{ id: 1, nombre: 'DEMO' }] })
    render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
    await screen.findByText(`Documento externo: ${long}`)
    expect(screen.queryByText('Guarda el borrador antes de añadir opciones.')).not.toBeInTheDocument()
    expect(within(screen.getByLabelText(/Entidad oferente ecuatoriana/).parentElement).getByRole('link')).toHaveAttribute('href', '/gestion/instituciones')
    const region = within(screen.getByRole('region', { name: 'Requisitos' }))
    await userEvent.click(region.getAllByRole('button', { name: 'Editar' })[1])
    expect(region.getByLabelText(/Descripción e instrucciones/)).toHaveValue(long)
    expect(region.getByLabelText('Nombre del documento')).toHaveValue('Segundo')
    region.getAllByRole('button', { name: 'Editar' }).forEach(button => expect(button).toBeDisabled())
    await userEvent.click(region.getByRole('button', { name: 'Cancelar' }))
    region.getAllByRole('button', { name: 'Editar' }).forEach(button => expect(button).toBeEnabled())
  })

  it('genera controles de regla de edad sin editor JSON', () => {
    const fields = requirementFields({ esquema_valor: { campos: { maximo: { label: 'Edad máxima', kind: 'integer', required: false } } } }, catalogs, [])
    render(<OfferForm fields={fields} onSubmit={vi.fn()} />)
    expect(screen.getByLabelText('Edad máxima')).toHaveAttribute('type', 'number')
    expect(screen.queryByLabelText(/JSON/)).not.toBeInTheDocument()
  })
})

it('la gestión de convocatorias del administrador no muestra la casilla de entidades no ecuatorianas', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : adminListing)
  render(<MemoryRouter initialEntries={['/gestion/convocatorias']}><Offers admin /></MemoryRouter>)
  await screen.findByRole('heading', { name: 'Filtros de búsqueda' })
  expect(screen.queryByLabelText('Incluir becas de entidades no ecuatorianas o sin confirmar')).not.toBeInTheDocument()
})
