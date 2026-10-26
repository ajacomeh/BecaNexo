import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OfferForm from './components/OfferForm'
import { requirementFields } from './pages/offerFields'

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [] }
it('configura niveles, grupo y destino con controles y conserva valores explícitos', async () => {
  const fields = requirementFields({ codigo: 'FORMACION', esquema_valor: { campos: { niveles_admitidos: { label: 'Niveles admitidos', kind: 'lista', required: false, options: ['grado', 'maestria'] } } } }, catalogs, [{ id: 4, nivel: 'maestria', modalidad: 'virtual' }])
  const save = vi.fn()
  render(<OfferForm fields={fields} initial={{ relacion_formacion: 'pendiente' }} onSubmit={save} />)
  await userEvent.click(screen.getByLabelText('grado'))
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Relación entre condiciones académicas' }), 'misma_formacion')
  await userEvent.type(screen.getByLabelText('Clave del grupo de misma formación'), 'titulo_promedio')
  await userEvent.selectOptions(screen.getByLabelText(/Destino específico/), '1')
  await userEvent.selectOptions(screen.getByLabelText(/Ámbito/), '4')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ regla_niveles_admitidos: ['grado'], relacion_formacion: 'misma_formacion', grupo_formacion: 'titulo_promedio', destino: 1, opcion_estudio: 4 }))
  expect(screen.queryByLabelText(/JSON/)).not.toBeInTheDocument()
})

it('edita equivalencias con procedencia sin JSON y muestra error de servidor sin éxito', async () => {
  const fields = requirementFields({ codigo: 'TITULO_AREA', esquema_valor: { campos: {} } }, catalogs, [])
  const save = vi.fn().mockRejectedValue({ message: 'Referencia no válida', fields: { equivalencias: 'Revisa las bases' } })
  render(<OfferForm fields={fields} onSubmit={save} />)
  await userEvent.click(screen.getByRole('button', { name: 'Añadir equivalencia' }))
  await userEvent.type(screen.getByLabelText('Nombre declarado equivalente'), 'Ing. Software')
  await userEvent.type(screen.getByLabelText('Nombre admitido en las bases'), 'Ingeniería de Software')
  await userEvent.type(screen.getByLabelText('Referencia que respalda la equivalencia'), 'Bases página 4')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ equivalencias: [{ tipo: 'titulo', origen: 'Ing. Software', admitido: 'Ingeniería de Software', referencia: 'Bases página 4', pais: null, provincia: null }] }))
  expect(await screen.findByText('Revisa las bases')).toBeVisible()
  expect(screen.queryByText('Cambios guardados.')).not.toBeInTheDocument()
})
