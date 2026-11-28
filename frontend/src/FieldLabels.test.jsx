import { expect, it } from 'vitest'
import { fieldLabel, requirementFields } from './pages/offerFields'

const formacion = { codigo: 'FORMACION', esquema_valor: { operadores: ['minimo'], campos: {
  nivel_minimo: { label: 'Mínimo original (sin lista admitida queda pendiente)', kind: 'text', required: false, options: ['bachillerato', 'grado'] },
  estado_exigido: { label: 'Estado exigido', kind: 'text', required: true, options: ['en_curso', 'concluidos'] } } } }

it('sustituye solo la etiqueta del nivel mínimo de FORMACION y conserva las demás del contrato', () => {
  expect(fieldLabel(formacion, 'nivel_minimo')).toBe('Nivel mínimo según las bases (sin lista de niveles admitidos, puede deducirse del texto)')
  expect(fieldLabel(formacion, 'estado_exigido')).toBe('Estado exigido')
  expect(fieldLabel({ ...formacion, codigo: 'IDIOMA', esquema_valor: { campos: { nivel_minimo: { label: 'Nivel MCER mínimo' } } } }, 'nivel_minimo')).toBe('Nivel MCER mínimo')
  expect(fieldLabel(undefined, 'nivel_minimo')).toBeUndefined()
})

it('el editor administrativo usa la misma etiqueta para el nivel mínimo de FORMACION', () => {
  const fields = requirementFields(formacion, { paises: [], areas: [], idiomas: [] }, [])
  expect(fields.find(f => f.name === 'regla_nivel_minimo').label).toBe('Nivel mínimo según las bases (sin lista de niveles admitidos, puede deducirse del texto)')
  expect(fields.find(f => f.name === 'regla_estado_exigido').label).toBe('Estado exigido')
})
