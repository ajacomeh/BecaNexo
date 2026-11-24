import { fieldIcon } from './scholarshipFields'

// Decorativo: el título ya nombra la beca. El tooltip indica el campo cuando es un icono de campo.
export default function ScholarshipIcon({ field }) {
  const { Glyph, field: known } = fieldIcon(field)
  return <span className="scholarship-icon" aria-hidden="true" title={known || undefined} data-field={known || 'beca'}>
    <Glyph focusable="false" size={18} strokeWidth={1.8} />
  </span>
}

/** Título de tarjeta con su icono a la izquierda, alineado con la primera línea. */
export function ScholarshipTitle({ as: Heading = 'h2', field, children }) {
  return <Heading className="scholarship-title"><ScholarshipIcon field={field} /><span className="scholarship-title-text">{children}</span></Heading>
}
