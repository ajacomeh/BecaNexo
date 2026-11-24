import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { BookOpen, BriefcaseBusiness, ConciergeBell, Cog, Cpu, FlaskConical, GraduationCap, Palette, Sprout, Stethoscope, Users } from 'lucide-react'
import { offersApi } from './api/client'
import { fieldIcon, singleArea } from './components/scholarshipFields'
import ScholarshipIcon from './components/ScholarshipIcon'
import CatalogCard from './components/CatalogCard'
import Offers from './pages/Offers'
import Favorites from './pages/Favorites'
import Notifications from './pages/Notifications'

const auth = vi.hoisted(() => ({ user: { nombre: 'Postulante', rol: 'postulante' } }))
vi.mock('./auth/context', () => ({ useAuth: () => ({ user: auth.user, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.user = { nombre: 'Postulante', rol: 'postulante' } })

const areas = [{ id: 1, nombre: 'Programas y certificaciones genéricos' }, { id: 2, nombre: 'Educación' }, { id: 10, nombre: 'Salud y bienestar' },
  { id: 7, nombre: 'Tecnologías de la información y la comunicación' }]
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas, idiomas: [], niveles: [], modalidades: [], tipos_beca: [], tipos_requisito: [] }
const offer = { id: 1, titulo: 'Beca sintética con un título largo que ocupa varias líneas en móvil', institucion: { nombre: 'Entidad' },
  estado: 'abierta', beneficios: [], opciones: [], areas: [10] }
// En el catálogo y en Convocatorias el icono va junto al título, en la columna de la cabecera; en el resto, dentro del título.
const iconOf = (heading) => heading.querySelector('.scholarship-icon') || heading.closest('.scholarship-header')?.querySelector('.scholarship-icon')

describe('mapa de campo a icono', () => {
  it.each([
    ['Educación', BookOpen], ['Artes y humanidades', Palette], ['Ciencias sociales, periodismo e información', Users],
    ['Administración de empresas y derecho', BriefcaseBusiness], ['Ciencias naturales, matemáticas y estadística', FlaskConical],
    ['Tecnologías de la información y la comunicación', Cpu], ['Ingeniería, industria y construcción', Cog],
    ['Agricultura, silvicultura, pesca y veterinaria', Sprout], ['Salud y bienestar', Stethoscope], ['Servicios', ConciergeBell],
  ])('%s', (field, glyph) => {
    expect(fieldIcon(field)).toEqual({ Glyph: glyph, field })
  })

  it('tolera mayúsculas, tildes y espacios; genéricos, desconocidos y vacíos usan el birrete', () => {
    expect(fieldIcon('  SALUD   Y BIENESTAR ').Glyph).toBe(Stethoscope)
    expect(fieldIcon('Educacion').Glyph).toBe(BookOpen)
    expect(fieldIcon('tecnologías de la informacion y la comunicacion').Glyph).toBe(Cpu)
    for (const value of ['Programas y certificaciones genéricos', 'Astronáutica recreativa', '', null, undefined]) {
      expect(fieldIcon(value)).toEqual({ Glyph: GraduationCap, field: null })
    }
  })

  it('regla: un área → su nombre; varias, ninguna o desconocida → null', () => {
    expect(singleArea([10], areas)).toBe('Salud y bienestar')
    expect(singleArea([10, 7], areas)).toBeNull()
    expect(singleArea([], areas)).toBeNull()
    expect(singleArea(undefined, areas)).toBeNull()
    expect(singleArea([99], areas)).toBeNull()
  })

  it('el icono es decorativo y solo los de campo llevan tooltip', () => {
    const { container, rerender } = render(<ScholarshipIcon field="Salud y bienestar" />)
    const icon = container.querySelector('.scholarship-icon')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
    expect(icon).toHaveAttribute('title', 'Salud y bienestar')
    expect(icon.querySelector('svg')).toHaveClass('lucide-stethoscope')
    rerender(<ScholarshipIcon field="Programas y certificaciones genéricos" />)
    expect(container.querySelector('.scholarship-icon')).not.toHaveAttribute('title')
    expect(container.querySelector('svg')).toHaveClass('lucide-graduation-cap')
  })
})

describe('aparece en las cuatro tarjetas sin cambiar el título', () => {
  it('catálogo público', () => {
    render(<MemoryRouter><CatalogCard offer={offer} catalogs={catalogs} /></MemoryRouter>)
    const heading = screen.getByRole('heading', { name: offer.titulo })
    expect(iconOf(heading)).toHaveAttribute('title', 'Salud y bienestar')
    cleanup()
    render(<MemoryRouter><CatalogCard offer={{ ...offer, areas: [10, 7] }} catalogs={catalogs} /></MemoryRouter>)
    expect(iconOf(screen.getByRole('heading', { name: offer.titulo })).querySelector('svg')).toHaveClass('lucide-graduation-cap')
  })

  it('Convocatorias (administración)', async () => {
    auth.user = { nombre: 'Admin', rol: 'administrador' }
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
      : { count: 2, page: 1, page_size: 12, results: [{ ...offer, id: 3, titulo: 'Beca TIC', areas: [7] }, { ...offer, id: 4, titulo: 'Beca sin área', areas: [] }] })
    render(<MemoryRouter><Offers admin /></MemoryRouter>)
    expect(iconOf(await screen.findByRole('heading', { name: 'Beca TIC' }))).toHaveAttribute('title', 'Tecnologías de la información y la comunicación')
    expect(iconOf(screen.getByRole('heading', { name: 'Beca sin área' })).querySelector('svg')).toHaveClass('lucide-graduation-cap')
  })

  it('Favoritos', async () => {
    vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'notificaciones' ? { no_leidas: 0 } : { count: 1, page_size: 12, results: [
      { id: 9, disponible: true, convocatoria: { id: 5, titulo: 'Beca favorita', institucion: 'Entidad', tipo_beca: null, estado: 'abierta', cierre: null, campo_conocimiento: 'Educación' } }] })
    render(<MemoryRouter><Favorites /></MemoryRouter>)
    const heading = await screen.findByRole('heading', { name: 'Beca favorita' })
    expect(iconOf(heading)).toHaveAttribute('aria-hidden', 'true')
    expect(iconOf(heading).querySelector('svg')).toHaveClass('lucide-book-open')
  })

  it('Notificaciones', async () => {
    vi.spyOn(offersApi, 'get').mockImplementation(async () => ({ count: 2, no_leidas: 2, page: 1, page_size: 10, results: [
      { id: 7, convocatoria_id: 42, titulo: 'Beca notificada', motivos: [], creada_en: '2026-11-07T14:00:00Z', leida_en: null, disponible: true, campo_conocimiento: 'Salud y bienestar' },
      { id: 8, convocatoria_id: 43, titulo: 'Beca sin campo', motivos: [], creada_en: '2026-11-07T14:00:00Z', leida_en: null, disponible: true, campo_conocimiento: null }] }))
    render(<MemoryRouter><Notifications /></MemoryRouter>)
    const heading = await screen.findByRole('heading', { name: 'Beca notificada', level: 3 })
    expect(iconOf(heading)).toHaveAttribute('title', 'Salud y bienestar')
    expect(within(screen.getByRole('heading', { name: 'Beca sin campo', level: 3 })).getByText('Beca sin campo')).toBeVisible()
    expect(iconOf(screen.getByRole('heading', { name: 'Beca sin campo', level: 3 })).querySelector('svg')).toHaveClass('lucide-graduation-cap')
  })
})
