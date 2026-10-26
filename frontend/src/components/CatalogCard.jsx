import { Link } from 'react-router-dom'
import FavoriteButton from './FavoriteButton'
import { stateLabel } from '../pages/offerDisplay'

import { readable, benefitSummary, unique } from '../pages/catalogPresentation'

export default function CatalogCard({ offer, catalogs }) {
  const options = offer.opciones
  const destinations = unique(options.flatMap(o => o.paises || []))
  const countries = destinations.map(id => catalogs.paises.find(p => p.id === id)?.nombre).filter(Boolean)
  const closing = offer.cierre ? new Intl.DateTimeFormat('es-EC', { dateStyle: 'medium', timeZone: 'America/Guayaquil' }).format(new Date(offer.cierre)) : null
  return <article className="offer-card catalog-card">
    {offer.estado !== 'sin_fecha' && <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>}
    <h2>{offer.titulo}</h2><p>{offer.institucion.nombre}</p>
    {offer.tipo_beca_nombre && <p>Tipo: {offer.tipo_beca_nombre}</p>}
    {benefitSummary(offer.beneficios).map((text, index) => <p className="accent-note" key={index}>{text}</p>)}
    {options.length === 1 && <p>{readable(options[0].nivel)} · {readable(options[0].modalidad)}</p>}
    {options.length > 1 && <div><p><strong>{options.length} opciones de estudio</strong></p><p>Niveles: {unique(options.map(o => readable(o.nivel))).join(', ')}</p><p>Modalidades disponibles: {unique(options.map(o => readable(o.modalidad))).join(', ')}</p><p className="small-note">Consulta las combinaciones de cada opción en el detalle.</p></div>}
    {destinations.length > 1 ? <p>{destinations.length} destinos</p> : countries.length === 1 && <p>Destino: {countries[0]}</p>}
    <p>{closing ? `Cierre: ${closing}` : offer.cierre_original?.trim() ? `Cierre según la fuente: ${offer.cierre_original}` : 'Fecha de cierre no informada'}</p>
    <div className="catalog-card-actions"><Link className="secondary-link catalog-detail-link" to={`/becas/${offer.id}`}>Ver detalle</Link><FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} /></div>
  </article>
}
