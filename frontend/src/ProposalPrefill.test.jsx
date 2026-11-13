import { expect, it } from 'vitest'
import { proposalPrefill } from './components/proposalPrefill'

const version = { datos_extraidos: {
  titulo: { texto_original: 'Beca nacional', url: 'https://siau.senescyt.gob.ec/ficha/' },
  descripcion: { texto_original: 'Dirigida a ciudadanos ecuatorianos.' },
  cierre: { original: '12 de noviembre, 2026', fecha: '2026-11-12' },
  estudios: { modalidad: { texto_original: 'En línea' }, destino: { texto_original: 'Ecuador' }, niveles_mencionados: [] },
  requisitos: { texto_original: 'Ser ciudadano ecuatoriano.' },
  beneficio: { texto_original: 'Cubre matrícula.', porcentajes: [] },
  entidad_html: { texto_original: 'Entidad mencionada' },
  enlaces_bases: [{ url: 'https://siau.senescyt.gob.ec/bases.zip' }],
} }
const docs = [{ rol: 'ficha_html', evidencia_id: 42 }, { rol: 'bases_pdf', evidencia_id: 43 }]

it('precarga literales e interpretaciones con evidencia HTML exacta sin confirmar entidad ni enlace', () => {
  const result = proposalPrefill(version, docs)
  expect(result.data).toMatchObject({ titulo: 'Beca nacional', descripcion: 'Dirigida a ciudadanos ecuatorianos.',
    cierre_original: '12 de noviembre, 2026', cierre_dia: '2026-11-12' })
  expect(result.data.institucion).toBeUndefined()
  expect(result.data.url_oficial).toBeUndefined()
  expect(result.data.opciones[0]).toMatchObject({ modalidad: 'En línea', destinos: 'Ecuador', ambito: 'pendiente', texto: '' })
  expect(result.data.beneficios[0]).toMatchObject({ texto: 'Cubre matrícula.', ambito: 'pendiente' })
  expect(result.data.requisitos[0]).toMatchObject({ texto: 'Ser ciudadano ecuatoriano.', ambito: 'pendiente' })
  expect(result.references.every((ref) => ref.evidencia_id === 42)).toBe(true)
  expect(result.references.find((item) => item.campo === 'cierre_dia').motivo).toContain('normalizada')
})

it('conserva ediciones existentes y no inventa candidatos cuando faltan datos o evidencia', () => {
  const result = proposalPrefill({ datos_extraidos: { ...version.datos_extraidos,
    titulo: { texto_original: '' }, cierre: { original: 'fecha pendiente', fecha: null },
    beneficio: {}, requisitos: {}, estudios: {} } }, [], { descripcion: 'Edición manual', opciones: [] })
  expect(result.data.descripcion).toBe('Edición manual')
  expect(result.data.opciones).toEqual([])
  expect(result.data.cierre_dia).toBeUndefined()
  expect(result.data.beneficios).toBeUndefined()
  expect(result.references).toEqual([])
})

it('omite textos demasiado extensos sin truncarlos silenciosamente', () => {
  const result = proposalPrefill({ datos_extraidos: { titulo: { texto_original: 'A'.repeat(251) },
    requisitos: { texto_original: 'R'.repeat(5001) } } }, docs)
  expect(result.data.titulo).toBeUndefined()
  expect(result.data.requisitos).toBeUndefined()
})
