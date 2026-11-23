import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { offersApi } from './api/client'
import OfferEditor from './pages/OfferEditor'
import { providerLabel } from './pages/offerDisplay'

vi.mock('./auth/context', () => ({ useAuth: () => ({ user: { nombre: 'Admin sintético', rol: 'administrador' }, logout: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [],
  niveles: [{ valor: 'maestria', nombre: 'Maestría' }], modalidades: [{ valor: 'virtual', nombre: 'Virtual' }] }

function draft(extra = {}) {
  return { id: 41, titulo: 'Beca de una universidad extranjera', institucion: null, revision: 'pendiente', estado: 'borrador', activa: true, version: 2,
    origen_automatico: { publicacion_id: 9, version_id: 30 }, descartado: false,
    aviso_oferente: 'Esta beca no corresponde a una entidad oferente ecuatoriana (oferente detectado: Universidad Extranjera)',
    oferente_externo: { no_ecuatoriano: true, nombre: 'Universidad Extranjera' }, opciones: [], beneficios: [], requisitos: [], ...extra }
}

function renderEditor(data) {
  vi.spyOn(offersApi, 'get').mockImplementation(async (path) => path === 'becas/catalogos' ? catalogs
    : path === 'gestion/convocatorias/41' ? data : path.endsWith('/origen') ? { aplicacion: null } : { count: 0, results: [] })
  render(<MemoryRouter initialEntries={['/gestion/convocatorias/41']}><Routes><Route path="/gestion/convocatorias/:id" element={<OfferEditor />} /></Routes></MemoryRouter>)
}

describe('publicar sin entidad oferente ecuatoriana', () => {
  it('muestra el aviso y exige «Publicar bajo mi responsabilidad» antes de enviar la confirmación', async () => {
    renderEditor(draft())
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue(draft({ revision: 'validada', estado: 'abierta' }))
    expect(await screen.findByText(/Esta beca no corresponde a una entidad oferente ecuatoriana/)).toBeVisible()
    const publish = screen.getByRole('button', { name: 'Validar y publicar' })
    expect(publish).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Publicar bajo mi responsabilidad' }))
    expect(publish).toBeEnabled()
    await userEvent.click(publish)
    expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/publicar', 'POST', { confirmar_oferente_no_ecuatoriano: true })
    expect(await screen.findByText('Convocatoria publicada.')).toBeVisible()
  })

  it('con entidad ecuatoriana asignada publica sin aviso ni confirmación adicional', async () => {
    renderEditor(draft({ institucion: { id: 1, nombre: 'Universidad Ecuatoriana' }, aviso_oferente: null, oferente_externo: null }))
    const write = vi.spyOn(offersApi, 'write').mockResolvedValue(draft({ revision: 'validada' }))
    const publish = await screen.findByRole('button', { name: 'Validar y publicar' })
    expect(screen.queryByRole('checkbox', { name: 'Publicar bajo mi responsabilidad' })).not.toBeInTheDocument()
    await userEvent.click(publish)
    expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/publicar', 'POST', {})
  })

  it('descarta el borrador con confirmación y permite restaurarlo', async () => {
    renderEditor(draft())
    const write = vi.spyOn(offersApi, 'write').mockResolvedValueOnce(draft({ descartado: true })).mockResolvedValueOnce(draft())
    await userEvent.click(await screen.findByRole('button', { name: 'Descartar borrador' }))
    expect(write).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar descarte' }))
    expect(write).toHaveBeenCalledWith('gestion/convocatorias/41/descartar', 'POST', {})
    expect(await screen.findByText(/Borrador descartado: no se publica/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Validar y publicar' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Restaurar borrador' }))
    expect(write).toHaveBeenLastCalledWith('gestion/convocatorias/41/restaurar', 'POST', {})
    expect(await screen.findByText('Borrador restaurado.')).toBeVisible()
  })
})

describe('rótulo del oferente en el catálogo público', () => {
  it('distingue entidad ecuatoriana, oferente no ecuatoriano y oferente por confirmar', () => {
    expect(providerLabel({ institucion: { nombre: 'Universidad Ecuatoriana' } })).toBe('Universidad Ecuatoriana')
    expect(providerLabel({ institucion: null, oferente_externo: { no_ecuatoriano: true, nombre: 'Universidad Extranjera' } }))
      .toBe('Oferente: Universidad Extranjera (no ecuatoriano)')
    expect(providerLabel({ institucion: null, oferente_externo: { no_ecuatoriano: true, nombre: null } })).toBe('Oferente por confirmar')
    expect(providerLabel({ institucion: null, oferente_externo: null })).toBe('Entidad oferente: No identificada')
  })
})
