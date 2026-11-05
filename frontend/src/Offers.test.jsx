import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import OfferForm from './components/OfferForm'
import { ApiError, offersApi } from './api/client'
import Offers from './pages/Offers'
import OfferEditor from './pages/OfferEditor'
import { RequirementList } from './pages/OfferDetail'
import { requirementFields } from './pages/offerFields'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }

describe('convocatorias', () => {
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
    expect(await screen.findByText('No hay convocatorias con estos filtros')).toBeVisible()
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
