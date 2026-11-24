import { fieldIcon } from './scholarshipFields'

// Decorativo: el título ya nombra la beca. El tooltip indica el campo cuando es un icono de campo.
// size="lg" (44 px) en las tarjetas del catálogo y de Convocatorias; por defecto 32 px (Favoritos, Notificaciones).
export default function ScholarshipIcon({ field, size }) {
  const { Glyph, field: known } = fieldIcon(field)
  return <span className={`scholarship-icon${size === 'lg' ? ' scholarship-icon-lg' : ''}`} aria-hidden="true" title={known || undefined} data-field={known || 'beca'}>
    <Glyph focusable="false" size={size === 'lg' ? 24 : 18} strokeWidth={1.8} />
  </span>
}

/** Título de tarjeta con su icono a la izquierda, alineado con la primera línea. */
export function ScholarshipTitle({ as: Heading = 'h2', field, size, children }) {
  return <Heading className={`scholarship-title${size === 'lg' ? ' scholarship-title-lg' : ''}`}><ScholarshipIcon field={field} size={size} /><span className="scholarship-title-text">{children}</span></Heading>
}

/** Cabecera de las tarjetas del catálogo y de Convocatorias: icono grande en su columna y, en la otra, el título y
 *  las líneas que lo acompañan (entidad, notas), todas con el mismo borde izquierdo, sin sangrías manuales. */
export function ScholarshipHeader({ as: Heading = 'h2', field, title, children }) {
  return <div className="scholarship-header"><ScholarshipIcon field={field} size="lg" />
    <div className="scholarship-header-text"><Heading className="scholarship-header-title">{title}</Heading>{children}</div></div>
}
