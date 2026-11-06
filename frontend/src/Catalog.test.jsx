import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { offersApi } from './api/client'
import PublicCatalog from './pages/PublicCatalog'
import CatalogCard from './components/CatalogCard'
import { BenefitList } from './pages/OfferDetail'
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
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '80', opcion_estudio: 1 }])[0]).toContain('Solo para una opción')
  const scoped = benefitSummary([{ concepto: 'Matrícula', porcentaje: '80', opcion_estudio: 1 }, { concepto: 'Matrícula', porcentaje: '20', opcion_estudio: 2 }])
  expect(scoped).toEqual(['Beneficios específicos por opción · Consulta las condiciones de cada opción en el detalle'])
})

it('cuenta opciones y destinos sin duplicados y no inventa combinaciones', () => {
  render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, opciones: [{ nivel: 'maestria', modalidad: 'virtual', paises: [1, 2] }, { nivel: 'maestria', modalidad: 'presencial', paises: [1] }] }} /></MemoryRouter>)
  expect(screen.getByText('2 opciones de estudio')).toBeVisible()
  expect(screen.getByText('Niveles: Maestría')).toBeVisible()
  expect(screen.getByText('Modalidades disponibles: Virtual, Presencial')).toBeVisible()
  expect(screen.getByText('2 destinos')).toBeVisible()
  expect(screen.getByText(/Consulta las combinaciones/)).toBeVisible()
})

it('conserva fecha local breve y texto de cierre registrado sin inferir permanencia', () => {
  const { rerender } = render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, estado: 'abierta', cierre: '2027-12-01T04:59:00Z' }} /></MemoryRouter>)
  expect(screen.getByText(/Cierre: 30 nov/)).toBeVisible()
  expect(screen.queryByText(/23:59|11:59/)).not.toBeInTheDocument()
  rerender(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, cierre_original: 'Convocatoria permanente según las bases' }} /></MemoryRouter>)
  expect(screen.getByText('Cierre según la fuente: Convocatoria permanente según las bases')).toBeVisible()
})

it('conserva error y reintento sin mostrar resultados obsoletos', async () => {
  vi.spyOn(offersApi, 'get').mockRejectedValueOnce(new Error('Error de prueba')).mockResolvedValue(catalogs)
  render(<MemoryRouter><PublicCatalog /></MemoryRouter>)
  expect(await screen.findByText('Error de prueba')).toBeVisible()
  vi.mocked(offersApi.get).mockImplementation(async path => path === 'becas/catalogos' ? catalogs : { results: [], count: 0, page: 1, page_size: 12 })
  await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('No hay convocatorias con estos filtros')).toBeVisible()
  const stateOptions = within(screen.getByLabelText('Estado')).getAllByRole('option', { hidden: true }).map(o => o.value)
  expect(stateOptions).toEqual(['', 'abierta', 'cierre_hoy', 'cerrada', 'proxima', 'sin_fecha'])
})

it('muestra día de cierre sin inventar hora ni estado de apertura', () => {
  render(<MemoryRouter><CatalogCard catalogs={catalogs} offer={{ ...offer, estado: 'cierre_hoy', cierre_dia: '2026-11-06', cierre_original: '6 de noviembre de 2026' }} /></MemoryRouter>)
  expect(screen.getByText('Cierra hoy · hora no informada')).toBeVisible()
  expect(screen.getByText(/Día de cierre: 6 nov/)).toHaveTextContent('hora no informada')
  expect(screen.queryByText(/23:59/)).not.toBeInTheDocument()
})

it('presenta el tope y advierte cuando la moneda no está confirmada', () => {
  expect(benefitSummary([{ concepto: 'Matrícula', porcentaje: '100.00', tope_original: '$3000', tope_moneda: null }])[0]).toContain('moneda no confirmada')
  render(<BenefitList records={[{ id: 1, concepto: 'Matrícula', porcentaje: '100.00', monto: null,
    tope_original: '$3000', tope_monto: '3000.00', tope_moneda: null }]} />)
  expect(screen.getByText(/Tope según las bases: \$3000/)).toHaveTextContent('Moneda no confirmada')
  expect(screen.queryByText(/3000.00 USD/)).not.toBeInTheDocument()
})
