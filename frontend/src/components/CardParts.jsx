import Icon from './Icon'

// Piezas de presentación comunes a las tarjetas del catálogo público y de Convocatorias (administración).

// Dato de la tarjeta: etiqueta con icono decorativo arriba y valor debajo (dentro de dl.offer-card-facts.card-facts).
export function CardFact({ icon, label, children }) {
  return <div><dt><Icon name={icon} />{label}</dt><dd>{children}</dd></div>
}

// Franja de beneficios de la tarjeta.
export function FinancingStrip({ items }) {
  return <div className="offer-card-financing"><h3>Financiamiento</h3>{items.map((text, index) => <p key={index}>{text}</p>)}</div>
}
