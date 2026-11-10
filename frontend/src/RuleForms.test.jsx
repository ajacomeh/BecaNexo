import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OfferForm from './components/OfferForm'
import { requirementFields, benefitFields, optionLabel } from './pages/offerFields'

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [] }
it('distingue opciones con igual nivel y modalidad en los ámbitos de beneficios y requisitos', async () => {
  const options = [
    { id: 4, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa A', institucion_destino: 'Institución A', paises: [1] },
    { id: 5, nivel: 'maestria', modalidad: 'virtual', programa: 'Programa B', institucion_destino: 'Institución B', paises: [1] },
  ]
  const fields = benefitFields(options, catalogs.paises)
  expect(fields[0].options.map(item => item.value)).toEqual([4, 5])
  expect(fields[0].options[0].label).toContain('Programa A · maestria / virtual · Institución A · Ecuador')
  expect(requirementFields({ codigo: 'DOCUMENTO', esquema_valor: { campos: {} } }, catalogs, options)[0].options[1].label).toContain('Programa B')
  const save = vi.fn()
  render(<OfferForm fields={fields} onSubmit={save} />)
  await userEvent.selectOptions(screen.getByLabelText(/Ámbito/), '5')
  await userEvent.type(screen.getByLabelText(/Concepto financiado/), 'Matrícula')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ opcion_estudio: 5 }))
  const same = [options[0], { ...options[0], id: 6 }]
  expect(optionLabel(same[0], catalogs.paises, same)).toContain('#4')
  expect(optionLabel(same[1], catalogs.paises, same)).toContain('#6')
})
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
