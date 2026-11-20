// Reproducción: un borrador con campos de alcance vacíos no debe enviar null,
// porque la API rechaza null en esos campos de texto (MAE_CONVOCATORIA no admite NULL).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import OfferForm from './components/OfferForm'
import { generalFields } from './pages/offerFields'

const catalogs = { tipos_beca: [], areas: [] }
const institutions = [{ id: 3, nombre: 'DEMO sintética' }]
const ALCANCE = ['alcance_detalle', 'alcance_exclusiones', 'alcance_sede', 'alcance_periodo']

it('no envía null en los campos de alcance vacíos de un borrador', async () => {
  const onSubmit = vi.fn().mockResolvedValue({})
  render(<OfferForm fields={generalFields(catalogs, institutions)}
    initial={{ titulo: 'Borrador sintético', institucion: 3, alcance_academico: 'pendiente' }} onSubmit={onSubmit} />)
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(onSubmit).toHaveBeenCalledTimes(1)
  const sent = onSubmit.mock.calls[0][0]
  for (const field of ALCANCE) expect(sent[field], field).not.toBeNull()
})
