import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { offersApi } from './api/client'
import CatalogCard from './components/CatalogCard'
import Offers from './pages/Offers'
import Favorites from './pages/Favorites'

const auth = vi.hoisted(() => ({ user: { nombre: 'Postulante', rol: 'postulante' } }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: auth.user, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.user = { nombre: 'Postulante', rol: 'postulante' } })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }, { id: 2, codigo: 'ES', nombre: 'España' }], areas: [{ id: 2, nombre: 'Educación' }],
  idiomas: [], niveles: [], modalidades: [], tipos_beca: [], tipos_requisito: [] }
const option = (id, nivel, paises = [1]) => ({ id, nivel, modalidad: 'virtual', activa: true, paises })
const offer = { id: 1, titulo: 'Beca sintética con un título largo', institucion: { nombre: 'Universidad Ecuatoriana' }, estado: 'abierta',
  cierre_dia: '2026-12-15', cierre_original: '15 de diciembre de 2026', areas: [2], opciones: [option(1, 'maestria', [2]), option(2, 'doctorado', [2])],
  beneficios: [{ id: 1, concepto: 'Matrícula', porcentaje: 50, opcion_estudio: null }] }

describe('tarjeta del catálogo público', () => {
  it('cabecera con icono grande, título, estado a la derecha y entidad alineada con el título', () => {
    render(<MemoryRouter><CatalogCard offer={offer} catalogs={catalogs} /></MemoryRouter>)
    const card = screen.getByRole('article')
    const head = card.querySelector('.card-head')
    const heading = within(head).getByRole('heading', { name: offer.titulo, level: 2 })
    expect(head.querySelector('.scholarship-icon-lg')).toHaveAttribute('aria-hidden', 'true')
    expect(head.querySelector('.card-head-status')).toHaveTextContent('Abierta')
    const provider = within(head).getByText('Universidad Ecuatoriana')
    expect(provider).toHaveClass('card-provider')
    expect(provider.querySelector('svg')).toBeNull() // sin icono de edificio
    expect(provider.parentElement).toBe(heading.parentElement) // misma columna de texto que el título
  })

  it('datos clave en cuadrícula con icono decorativo y pie con «Ver detalle» al fondo', () => {
    render(<MemoryRouter><CatalogCard offer={offer} catalogs={catalogs} /></MemoryRouter>)
    const card = screen.getByRole('article')
    const facts = card.querySelector('dl.card-facts')
    for (const label of ['Cierre', 'Opciones de estudio', 'Destino']) {
      const term = within(facts).getByText(label)
      expect(term.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(term.nextElementSibling.tagName).toBe('DD')
    }
    expect(within(facts).getByText('España')).toBeVisible()
    expect(within(card).getByText('Financiamiento')).toBeVisible()
    const foot = card.querySelector('.card-foot')
    expect(foot).toBe(card.lastElementChild)
    expect(within(foot).getByText('Consulta las condiciones de cada opción en el detalle.')).toBeVisible()
    expect(within(foot).getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/becas/1')
  })
})

describe('tarjeta de Convocatorias (administración)', () => {
  const draft = { ...offer, id: 7, titulo: 'Borrador del rastreo', estado: 'borrador', revision: 'pendiente', institucion: null, beneficios: [],
    oferente_externo: { no_ecuatoriano: true, nombre: 'Universidad Extranjera' }, origen_automatico: { publicacion_id: 17 }, tipo_beca_nombre: null,
    diagnostico: { faltan: 1 }, descartado: true }
  const ready = { ...offer, id: 8, titulo: 'Convocatoria lista', estado: 'borrador', revision: 'pendiente', tipo_beca_nombre: 'Mérito académico', diagnostico: { faltan: 0 } }

  it('cabecera, oferente alineado con el título, franja de revisión y datos compactos con los mismos textos', async () => {
    auth.user = { nombre: 'Admin', rol: 'administrador' }
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : { count: 2, page: 1, page_size: 12, results: [draft, ready] })
    render(<MemoryRouter><Offers admin /></MemoryRouter>)
    const card = (await screen.findByRole('heading', { name: 'Borrador del rastreo' })).closest('article')
    expect(card).toHaveClass('admin-offer-card')
    const head = card.querySelector('.card-head')
    const heading = within(head).getByRole('heading', { name: 'Borrador del rastreo' })
    expect(head.querySelector('.scholarship-icon-lg')).toHaveAttribute('aria-hidden', 'true')
    const status = head.querySelector('.card-head-status')
    expect(within(status).getByText('Borrador')).toBeVisible()
    expect(within(status).getByText('Borrador descartado')).toBeVisible()
    const oferente = within(head).getByText('Oferente: Universidad Extranjera (no ecuatoriano)')
    expect(oferente.querySelector('svg')).toBeNull()
    expect(oferente.parentElement).toBe(heading.parentElement)
    const origen = within(head).getByText('Borrador del rastreo · Publicación 17')
    expect(origen).toHaveClass('small-note')
    expect(origen.parentElement).toBe(heading.parentElement)
    expect(within(card).getByText('Faltan 1 paso para publicar')).toHaveClass('card-readiness-pending')
    // Datos con la misma presentación que el catálogo: icono decorativo, etiqueta (dt) y valor (dd); mismos textos.
    const facts = card.querySelector('dl.offer-card-facts.card-facts')
    const values = { 'Opciones de estudio': '2', Niveles: 'Maestría, Doctorado', Modalidades: 'Virtual' }
    for (const [label, value] of Object.entries(values)) {
      const term = within(facts).getByText(label, { selector: 'dt' })
      expect(term.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
      expect(term.nextElementSibling).toHaveTextContent(new RegExp(`^${value}$`))
    }
    expect(within(facts).getByText('Cierre', { selector: 'dt' }).nextElementSibling.tagName).toBe('DD')
    expect(within(facts).queryByText('Tipo', { selector: 'dt' })).not.toBeInTheDocument()
    const financing = card.querySelector('.offer-card-financing')
    expect(within(financing).getByText('Financiamiento')).toBeVisible()
    expect(within(financing).getByText('Beneficios: no publicados en la ficha')).toBeVisible()
    const foot = card.querySelector('.card-foot')
    expect(foot).toBe(card.lastElementChild)
    const edit = within(foot).getByRole('link', { name: 'Editar y revisar' })
    expect(edit).toHaveAttribute('href', '/gestion/convocatorias/7')
    expect(edit).toHaveClass('catalog-detail-link')
    expect(edit.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    const listo = screen.getByRole('heading', { name: 'Convocatoria lista' }).closest('article')
    expect(within(listo).getByText('Sin pendientes: lista para revisar y publicar')).toHaveClass('card-readiness-ready')
    expect(within(listo).getByText('Tipo', { selector: 'dt' }).nextElementSibling).toHaveTextContent(/^Mérito académico$/)
  })
})

it('Favoritos conserva su icono de tamaño normal', async () => {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'notificaciones' ? { no_leidas: 0 } : { count: 1, page_size: 12, results: [
    { id: 9, disponible: true, convocatoria: { id: 5, titulo: 'Beca favorita', institucion: 'Entidad', tipo_beca: null, estado: 'abierta', cierre: null, campo_conocimiento: null } }] })
  render(<MemoryRouter><Favorites /></MemoryRouter>)
  const icon = (await screen.findByRole('heading', { name: 'Beca favorita' })).querySelector('.scholarship-icon')
  expect(icon).not.toHaveClass('scholarship-icon-lg')
  expect(icon.closest('article')).not.toHaveClass('catalog-card')
})

it('«Oferente por confirmar» se muestra igual, en la columna del título', async () => {
  auth.user = { nombre: 'Admin', rol: 'administrador' }
  const sinNombre = { ...offer, id: 11, titulo: 'Borrador sin oferente', estado: 'borrador', revision: 'pendiente', institucion: null,
    oferente_externo: { no_ecuatoriano: false, nombre: null }, origen_automatico: { publicacion_id: 30 } }
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs : { count: 1, page: 1, page_size: 12, results: [sinNombre] })
  render(<MemoryRouter><Offers admin /></MemoryRouter>)
  const heading = await screen.findByRole('heading', { name: 'Borrador sin oferente' })
  expect(screen.getByText('Oferente por confirmar').parentElement).toBe(heading.parentElement)
})
