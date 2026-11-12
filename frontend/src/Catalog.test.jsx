import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import PublicCatalog from './pages/PublicCatalog'
import CatalogCard from './components/CatalogCard'
import OfferDetail, { BenefitList, RequirementList } from './pages/OfferDetail'
import { benefitSummary } from './pages/catalogPresentation'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: null }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }], niveles: [{ valor: 'grado', nombre: 'Grado' }], modalidades: [{ valor: 'virtual', nombre: 'Virtual' }], tipos_beca: [{ id: 1, nombre: 'Mérito' }] }
const offer = { id: 1, titulo: 'DEMOSTRACIÓN · Oferta', institucion: { nombre: 'Entidad' }, estado: 'sin_fecha', beneficios: [], opciones: [] }
function Location() { return <output data-testid="url">{useLocation().search}</output> }
function setup(path = '/becas', count = 25) {
  const get = vi.spyOn(offersApi, 'get').mockImplementation(async (path, p) => path === 'becas/catalogos' ? catalogs : { count, page_size: 12, page: Number(p.page || 1), results: count ? [offer] : [] })
  render(<MemoryRouter initialEntries={[path]}><PublicCatalog /><Location /></MemoryRouter>)
  return get
}

it('aplica filtros, conserva secundarios al cerrar y limpia filtros, orden y página', async () => {
  setup('/becas?page=2&orden=titulo&estado=abierta')
  const u = userEvent.setup()
  await screen.findByText('Más filtros · 1 aplicados')
  await u.click(screen.getByText('Más filtros · 1 aplicados'))
  await u.selectOptions(screen.getByLabelText('Tipo de beca'), '1')
  await u.click(screen.getByText('Más filtros · 1 aplicados'))
  await u.type(screen.getByLabelText('Buscar título, institución o área'), 'ingeniería')
  await u.selectOptions(screen.getByLabelText('Nivel'), 'grado')
  await u.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  expect(screen.getByTestId('url').textContent).toContain('tipo_beca=1')
  expect(screen.getByTestId('url').textContent).toContain('orden=titulo')
  expect(screen.getByTestId('url').textContent).not.toContain('page=')
  await screen.findByText('Más filtros · 2 aplicados')
  await u.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
  expect(screen.getByTestId('url')).toBeEmptyDOMElement()
  expect(screen.getByLabelText('Nivel')).toHaveValue('')
  expect(await screen.findByLabelText(/Ordenar por/)).toHaveValue('recientes')
})

it('ordena inmediatamente, vuelve a página uno y conserva filtros aplicados', async () => {
  const get = setup('/becas?page=2&nivel=grado')
  const u = userEvent.setup()
  await u.selectOptions(await screen.findByLabelText(/Ordenar por/), 'cierre')
  expect(screen.getByTestId('url').textContent).toContain('nivel=grado')
  expect(screen.getByTestId('url').textContent).not.toContain('page=')
  expect(get).toHaveBeenCalledWith('becas', { nivel: 'grado', orden: 'cierre' })
  await u.click(await screen.findByRole('button', { name: 'Siguiente' }))
  expect(screen.getByTestId('url').textContent).toContain('page=2')
})

it.each([0, 1, 12])('oculta paginación según metadatos count=%i, no según tarjetas', async count => {
  setup('/becas', count)
  await screen.findByLabelText(/Ordenar por/)
  expect(screen.queryByRole('navigation', { name: 'Paginación', exact: true })).not.toBeInTheDocument()
})

it('distingue catálogo vacío de búsqueda sin coincidencias', async () => {
  const u = userEvent.setup()
  setup('/becas', 0)
  expect(await screen.findByText('No hay convocatorias disponibles actualmente')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Restablecer filtros' })).not.toBeInTheDocument()
  await u.type(screen.getByLabelText('Buscar título, institución o área'), 'inexistente')
  await u.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  expect(await screen.findByText('No encontramos becas que coincidan con los filtros seleccionados')).toBeVisible()
  await u.click(screen.getByRole('button', { name: 'Restablecer filtros' }))
  expect(await screen.findByText('No hay convocatorias disponibles actualmente')).toBeVisible()
})

it('omite datos vacíos, muestra una sola ausencia de cierre y conserva retorno seguro de favoritos', () => {
  render(<MemoryRouter><CatalogCard offer={offer} catalogs={catalogs} /></MemoryRouter>)
  expect(screen.getAllByText('Fecha de cierre no informada')).toHaveLength(1)
  expect(screen.queryByText(/No especificado|Beneficios no especificados|Opciones no especificadas/)).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/becas/1')
  expect(screen.getByRole('link', { name: 'Guardar en favoritos' })).toHaveAttribute('href', '/login?next=%2Fbecas%2F1')
})

it('distingue porcentajes comunes, apoyo sin porcentaje y alcance por opción', () => {
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '80.00' }])).toEqual(['80 % de matrícula'])
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '80.50' }])).toEqual(['80.5 % de matrícula'])
  expect(benefitSummary([{ concepto: 'Matrícula', monto: '1000.00' }])).toEqual(['Apoyo para matrícula · Consulta las condiciones'])
  expect(benefitSummary([{ concepto: 'Matrícula', monto: '1000.00', moneda: 'USD' }])).toEqual(['1000.00 USD para matrícula'])
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '80', opcion_estudio: 1 }])[0]).toContain('Solo para una opción')
  const scoped = benefitSummary([{ concepto: 'Matrícula', porcentaje: '80', opcion_estudio: 1 }, { concepto: 'Matrícula', porcentaje: '20', opcion_estudio: 2 }])
  expect(scoped).toEqual(['Beneficios específicos por opción · Consulta las condiciones de cada opción en el detalle'])
})

it('cuenta opciones y destinos sin duplicados y no inventa combinaciones', () => {
  render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, opciones: [{ nivel: 'maestria', modalidad: 'virtual', paises: [1, 2] }, { nivel: 'maestria', modalidad: 'presencial', paises: [1] }] }} /></MemoryRouter>)
  expect(screen.getByText('Opciones de estudio').nextElementSibling).toHaveTextContent('2 · Maestría · Virtual, Presencial')
  expect(screen.getByText('Destinos').nextElementSibling).toHaveTextContent('Ecuador, España')
  expect(screen.getByText(/Consulta las condiciones de cada opción/)).toBeVisible()
})

it('conserva fecha local breve y texto de cierre registrado sin inferir permanencia', () => {
  const { rerender } = render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, estado: 'abierta', cierre: '2027-12-01T04:59:00Z' }} /></MemoryRouter>)
  expect(screen.getByText('Cierre').nextElementSibling).toHaveTextContent(/30 nov/)
  expect(screen.queryByText(/23:59|11:59/)).not.toBeInTheDocument()
  rerender(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, cierre_original: 'Convocatoria permanente según las bases' }} /></MemoryRouter>)
  expect(screen.getByText('Cierre').nextElementSibling).toHaveTextContent('Convocatoria permanente según las bases')
})

it('conserva error y reintento sin mostrar resultados obsoletos', async () => {
  vi.spyOn(offersApi, 'get').mockRejectedValueOnce(new Error('Error de prueba')).mockResolvedValue(catalogs)
  render(<MemoryRouter><PublicCatalog /></MemoryRouter>)
  expect(await screen.findByText('Error de prueba')).toBeVisible()
  vi.mocked(offersApi.get).mockImplementation(async path => path === 'becas/catalogos' ? catalogs : { results: [], count: 0, page: 1, page_size: 12 })
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('No hay convocatorias disponibles actualmente')).toBeVisible()
  const stateOptions = within(screen.getByLabelText('Estado')).getAllByRole('option', { hidden: true }).map(o => o.value)
  expect(stateOptions).toEqual(['', 'abierta', 'cierre_hoy', 'cerrada', 'proxima', 'sin_fecha'])
})

it('muestra día de cierre sin inventar hora ni estado de apertura', () => {
  render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, estado: 'cierre_hoy', cierre_dia: '2026-11-06', cierre_original: '6 de noviembre de 2026' }} /></MemoryRouter>)
  expect(screen.getByText('Cierra hoy · hora no informada')).toBeVisible()
  expect(screen.getByText('Cierre').nextElementSibling).toHaveTextContent('6 nov 2026 · hora no informada')
  expect(screen.queryByText(/23:59/)).not.toBeInTheDocument()
})

it('presenta el tope y advierte cuando la moneda no está confirmada', () => {
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '100.00', tope_original: '$3000', tope_moneda: null }])[0]).toContain('moneda no confirmada')
  render(<BenefitList records={[{ id: 1, concepto: 'Matrícula', porcentaje: '100.00', monto: null,
    tope_original: '$3000', tope_monto: '3000.00', tope_moneda: null }]} />)
  expect(screen.getByText(/Tope según las bases: \$3000/)).toHaveTextContent('Moneda no confirmada')
  expect(screen.queryByText(/3000.00 USD/)).not.toBeInTheDocument()
})

it('destaca el enlace oficial válido y conserva ámbitos y precisión en el detalle', async () => {
  const detail = { ...offer, estado: 'cierre_hoy', cierre_dia: '2026-11-06', cierre_original: '6 de noviembre de 2026',
    url_oficial: 'https://example.org/convocatoria', url_bases: 'https://example.org/convocatoria', descripcion: 'Descripción revisada', tipo_beca_nombre: 'Mérito',
    opciones: [{ id: 4, programa: 'Programa A', nivel: 'maestria', modalidad: 'virtual', paises: [1] }],
    beneficios: [{ id: 5, concepto: 'Matrícula', porcentaje: '80.00', opcion_estudio: 4 }], requisitos: [], institucion: { nombre: 'Entidad' } }
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? catalogs : detail)
  render(<MemoryRouter initialEntries={['/becas/1']}><Routes><Route path="/becas/:id" element={<OfferDetail />} /></Routes></MemoryRouter>)
  const link = await screen.findByRole('link', { name: 'Ver convocatoria oficial' })
  expect(link).toHaveAttribute('href', detail.url_oficial)
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.queryByRole('link', { name: 'Consultar bases oficiales' })).not.toBeInTheDocument()
  expect(screen.getByText('Cierre').nextElementSibling).toHaveTextContent('hora no informada')
  expect(screen.getByText('Financiamiento').nextElementSibling).toHaveTextContent('Solo para una opción')
  expect(screen.getByText('Beneficios comunes').parentElement).not.toHaveTextContent('80.00')
  expect(screen.getByText(/Beneficios específicos de esta opción/).parentElement).toHaveTextContent('80.00')
})

it('identifica una beca ficticia sin presentar sus enlaces de ejemplo como oficiales', async () => {
  const detail = { ...offer, titulo: 'Beca de demostración (Ficticia)', descripcion: 'DEMOSTRACIÓN',
    url_oficial: 'https://example.org/demo', url_bases: 'https://example.org/demo/bases', requisitos: [] }
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? catalogs : detail)
  render(<MemoryRouter initialEntries={['/becas/1']}><Routes><Route path="/becas/:id" element={<OfferDetail />} /></Routes></MemoryRouter>)
  expect(await screen.findByText(/Convocatoria ficticia para demostración/)).toBeVisible()
  expect(screen.getByText(/No existen bases ni postulación reales/)).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Ver convocatoria oficial' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Consultar bases oficiales' })).not.toBeInTheDocument()
})

it('mantiene separados los datos de dos opciones y permite consultar paneles y referencias', async () => {
  const optionCatalogs = { ...catalogs, tipos_requisito: [
    { id: 1, codigo: 'EDAD', nombre: 'Edad', esquema_valor: { campos: { minimo: { label: 'Edad mínima' } } } },
    { id: 2, codigo: 'DOCUMENTO', nombre: 'Documento externo', esquema_valor: { campos: {} } },
  ] }
  const detail = { ...offer, descripcion: 'Condiciones de prueba', institucion: { nombre: 'Entidad' },
    opciones: [{ id: 4, programa: 'Programa A', nivel: 'maestria', modalidad: 'virtual', paises: [1], duracion_meses: 12 },
      { id: 5, programa: 'Programa B', nivel: 'grado', modalidad: 'presencial', paises: [2], institucion_destino: 'Universidad de prueba' }],
    beneficios: [{ id: 10, opcion_estudio: 4, concepto: 'Matrícula', porcentaje: '80.00' },
      { id: 11, opcion_estudio: 5, concepto: 'Transporte', monto: '500.00', moneda: 'USD' },
      { id: 12, opcion_estudio: null, concepto: 'Materiales', porcentaje: '20.00' }],
    requisitos: [{ id: 20, opcion_estudio: 4, tipo_requisito: 1, obligatorio: true, texto_original: 'Edad mínima de 21 años',
      valor_estructurado: { minimo: 21 }, referencia_bases: 'Sección 4', modo_comprobacion: 'datos_declarados' },
    { id: 21, opcion_estudio: 5, tipo_requisito: 2, obligatorio: true, texto_original: 'Presentar certificado original',
      valor_estructurado: { documento: 'Certificado de estudios', condiciones: 'Original o copia certificada' } },
    { id: 22, opcion_estudio: null, tipo_requisito: 2, obligatorio: true, texto_original: 'Identificación vigente',
      valor_estructurado: { documento: 'Documento de identidad' } }] }
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? optionCatalogs : detail)
  render(<MemoryRouter initialEntries={['/becas/1']}><Routes><Route path="/becas/:id" element={<OfferDetail />} /></Routes></MemoryRouter>)
  const first = await screen.findByRole('article', { name: 'Opción 1: Programa A' })
  const second = screen.getByRole('article', { name: 'Opción 2: Programa B' })
  expect(within(first).getByText('Duración').nextElementSibling).toHaveTextContent('12 meses')
  expect(within(second).getByText('Institución de destino').nextElementSibling).toHaveTextContent('Universidad de prueba')
  expect(within(first).getByText('Edad mínima de 21 años')).toBeVisible()
  const firstBenefits = within(first).getByText(/Beneficios específicos de esta opción/).closest('details')
  const secondBenefits = within(second).getByText(/Beneficios específicos de esta opción/).closest('details')
  expect(firstBenefits.open).toBe(false)
  await userEvent.click(within(first).getByText(/Beneficios específicos de esta opción/))
  expect(firstBenefits.open).toBe(true)
  expect(firstBenefits).toHaveTextContent('80.00 %')
  expect(firstBenefits).not.toHaveTextContent('500.00 USD')
  expect(firstBenefits).not.toHaveTextContent('20.00 %')
  await userEvent.click(within(second).getByText(/Beneficios específicos de esta opción/))
  expect(secondBenefits).toHaveTextContent('500.00 USD')
  expect(secondBenefits).not.toHaveTextContent('80.00 %')
  expect(screen.getByText('Beneficios comunes').parentElement).toHaveTextContent('20.00 %')
  const documentPanel = within(second).getByText(/Referencias, documentos y verificación/).closest('details')
  expect(documentPanel.open).toBe(false)
  await userEvent.click(within(second).getByText(/Referencias, documentos y verificación/))
  expect(documentPanel.open).toBe(true)
  expect(documentPanel).toHaveTextContent('Certificado de estudios')
  expect(documentPanel).toHaveTextContent('Original o copia certificada')
  expect(documentPanel).not.toHaveTextContent('Documento de identidad')
  expect(within(first).queryByText('Certificado de estudios')).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Documentación requerida', level: 2 }).closest('section')).toHaveClass('profile-card', 'offer-documents-common')
  expect(screen.getByText('Documentos comunes a la convocatoria').parentElement).toHaveTextContent('Documento de identidad')
  const source = within(first).getByText('Referencia y evidencia en las bases').closest('details')
  await userEvent.click(within(first).getByText('Referencia y evidencia en las bases'))
  expect(source.open).toBe(true)
  expect(source).toHaveTextContent('Sección 4')
})

it('agrupa la verificación común y conserva las condiciones y referencias por requisito', () => {
  const requirementCatalogs = { ...catalogs, tipos_requisito: [{ id: 1, nombre: 'Edad', esquema_valor: { campos: { minimo: { label: 'Edad mínima' } } } }, { id: 2, nombre: 'Dedicación', esquema_valor: { campos: {} } }] }
  const rows = [
    { id: 1, tipo_requisito: 1, obligatorio: true, texto_original: 'Mayor de 21 años', valor_estructurado: { minimo: 21 }, modo_comprobacion: 'datos_declarados', referencia_bases: 'Sección 1', grupo_formacion: 'academico_E_0' },
    { id: 2, tipo_requisito: 2, obligatorio: true, texto_original: 'Tiempo parcial disponible', modo_comprobacion: 'datos_declarados', referencia_bases: 'Sección 2', grupo_formacion: 'academico_E_0' },
  ]
  const { rerender } = render(<RequirementList records={rows} catalogs={requirementCatalogs} />)
  expect(screen.getAllByText(/Para todos los requisitos de este grupo/)).toHaveLength(1)
  expect(screen.getByText('Mayor de 21 años')).toBeVisible()
  expect(screen.getByText('Tiempo parcial disponible')).toBeVisible()
  expect(screen.getByText('Edad mínima').nextElementSibling).toHaveTextContent('21')
  expect(screen.getByText('Los requisitos con el mismo grupo académico deben cumplirse con una misma formación.')).toBeVisible()
  expect(screen.getAllByText('Grupo académico 1')).toHaveLength(2)
  expect(screen.queryByText(/academico_E_0/)).not.toBeInTheDocument()
  const references = screen.getAllByText('Referencia y evidencia en las bases').map(node => node.closest('details'))
  expect(references.every(panel => !panel.open)).toBe(true)
  expect(references[0]).toHaveTextContent('Sección 1')
  expect(references[1]).toHaveTextContent('Sección 2')
  rerender(<RequirementList records={[rows[0], { ...rows[1], modo_comprobacion: 'entidad_oferente', detalle_acreditacion: 'Presentar certificado firmado' }]} catalogs={requirementCatalogs} />)
  expect(screen.queryByText(/Para todos los requisitos de este grupo/)).not.toBeInTheDocument()
  expect(screen.getByText('Presentar certificado firmado', { exact: false })).toBeVisible()
  expect(screen.getByText(/Verificación externa por la entidad oferente/)).toBeVisible()
})

it('no ofrece un enlace oficial falso o inseguro', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async path => path === 'becas/catalogos' ? catalogs : { ...offer, url_oficial: 'javascript:alert(1)', descripcion: 'Descripción', requisitos: [] })
  render(<MemoryRouter initialEntries={['/becas/1']}><Routes><Route path="/becas/:id" element={<OfferDetail />} /></Routes></MemoryRouter>)
  expect(await screen.findByText(/El enlace oficial no está disponible/)).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Ver convocatoria oficial' })).not.toBeInTheDocument()
})
