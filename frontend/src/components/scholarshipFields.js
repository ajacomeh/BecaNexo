import { BookOpen, BriefcaseBusiness, ConciergeBell, Cog, Cpu, FlaskConical, GraduationCap, Palette, Sprout, Stethoscope, Users } from 'lucide-react'

// Campos amplios del catálogo CAT_AREA (Senescyt), comparados sin mayúsculas ni tildes.
// «Programas y certificaciones genéricos» y cualquier nombre nuevo usan el birrete genérico de beca.
const clave = (texto) => String(texto ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()

export const FIELD_ICONS = {
  [clave('Educación')]: BookOpen,
  [clave('Artes y humanidades')]: Palette,
  [clave('Ciencias sociales, periodismo e información')]: Users,
  [clave('Administración de empresas y derecho')]: BriefcaseBusiness,
  [clave('Ciencias naturales, matemáticas y estadística')]: FlaskConical,
  [clave('Tecnologías de la información y la comunicación')]: Cpu,
  [clave('Ingeniería, industria y construcción')]: Cog,
  [clave('Agricultura, silvicultura, pesca y veterinaria')]: Sprout,
  [clave('Salud y bienestar')]: Stethoscope,
  [clave('Servicios')]: ConciergeBell,
}

/** Icono del campo de conocimiento; el birrete si no hay campo o no se reconoce. */
export function fieldIcon(field) {
  const glyph = FIELD_ICONS[clave(field)]
  return glyph ? { Glyph: glyph, field } : { Glyph: GraduationCap, field: null }
}

/** Nombre del área única de la convocatoria (ids de `areas` y el catálogo de áreas); null si hay varias o ninguna. */
export function singleArea(areaIds, catalogAreas = []) {
  if (!Array.isArray(areaIds) || areaIds.length !== 1) return null
  return catalogAreas.find((area) => area.id === areaIds[0])?.nombre ?? null
}
