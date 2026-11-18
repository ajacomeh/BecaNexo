import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import OriginPanel from './components/OriginPanel'
import OfferForm from './components/OfferForm'
import { offersApi } from './api/client'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('permite preparar una propuesta individual sin escribir ni preparar alternativas', async () => {
  const write = vi.spyOn(offersApi, 'write')
  vi.spyOn(offersApi, 'get').mockResolvedValue({ aplicacion: null, automatico: true,
    publicacion_id: 4, version_id: 8, bloqueos_actuales: [], datos_iniciales: {},
    candidatos_editables: { requisitos: [], opciones: [], otros_campos: { propuestas_documentales: [
      { campo: 'cierre_dia', valor: '2026-11-12', texto_original: 'Cierre de postulaciones 12/11/2026',
        destino: 'general', estado: 'pendiente_revision', advertencias: [],
        procedencia: { version_id: 8, documento_id: 2, pagina: 3, url: 'https://institucion.edu.ec/bases.pdf' } },
      { campo: 'requisito', valor: 'Acreditar discapacidad', texto_original: 'Acreditar discapacidad',
        destino: null, estado: 'pendiente_revision', advertencias: ['Alternativa'],
        categoria: 'Beca Solidaridad', procedencia: { version_id: 8, documento_id: 2, pagina: 4 } },
    ] } } })
  const onPrepare = vi.fn()
  render(<MemoryRouter><OriginPanel offer={{ id: 9, version: 1 }} onPrepare={onPrepare} /></MemoryRouter>)
  await userEvent.setup().click(await screen.findByText('Propuestas documentales para revisar (2)'))
  expect(screen.getAllByText(/Documento 2 · Versión 8/)).toHaveLength(2)
  expect(screen.getByText(/Categoría: Beca Solidaridad/)).toBeVisible()
  await userEvent.setup().click(screen.getByRole('button', { name: 'Preparar en editor' }))
  expect(onPrepare).toHaveBeenCalledWith('general', { campo: 'cierre_dia', valor: '2026-11-12' })
  expect(write).not.toHaveBeenCalled()
})

it('aplica una propuesta solo a un campo vacío y conserva una edición existente', async () => {
  const fields = [{ name: 'cierre_dia', label: 'Día de cierre', type: 'date' }]
  const proposal = { campo: 'cierre_dia', valor: '2026-11-12' }
  const save = vi.fn()
  const { rerender } = render(<OfferForm fields={fields} proposal={proposal} onSubmit={save} />)
  expect(screen.getByLabelText('Día de cierre')).toHaveValue('')
  await userEvent.setup().click(screen.getByRole('button', { name: 'Usar propuesta en campo vacío' }))
  expect(screen.getByLabelText('Día de cierre')).toHaveValue('2026-11-12')
  expect(save).not.toHaveBeenCalled()
  rerender(<OfferForm fields={fields} proposal={{ campo: 'cierre_dia', valor: '2026-12-01' }} onSubmit={save} />)
  expect(screen.getByLabelText('Día de cierre')).toHaveValue('2026-11-12')
  expect(screen.getByRole('button', { name: 'Usar propuesta en campo vacío' })).toBeDisabled()
})
