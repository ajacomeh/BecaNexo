import Icon from './Icon'
import { Link } from 'react-router-dom'
import FavoriteButton from './FavoriteButton'
import { stateLabel, closingText } from '../pages/offerDisplay'

import { readable, benefitSummary, unique } from '../pages/catalogPresentation'

export default function CatalogCard({ offer, catalogs }) {
  const options = offer.opciones
  const destinations = unique(options.flatMap(o => o.paises || []))
  const countries = destinations.map(id => catalogs.paises.find(p => p.id === id)?.nombre).filter(Boolean)
  const financing = benefitSummary(offer.beneficios)
  return <article className="offer-card catalog-card">
    <div className="offer-card-heading">{offer.estado !== 'sin_fecha' && <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>}<h2>{offer.titulo}</h2><p className="offer-provider">{offer.institucion.nombre}</p></div>
    <dl className="offer-card-facts"><div><dt>Cierre</dt><dd>{closingText(offer, true)}</dd></div>
      {options.length === 1 && <><div><dt>Nivel y modalidad</dt><dd>{readable(options[0].nivel)} · {readable(options[0].modalidad)}</dd></div></>}
      {options.length > 1 && <div><dt>Opciones de estudio</dt><dd>{options.length} · {unique(options.map(o => readable(o.nivel))).join(', ')} · {unique(options.map(o => readable(o.modalidad))).join(', ')}</dd></div>}
      {countries.length > 0 && <div><dt>{countries.length === 1 ? 'Destino' : 'Destinos'}</dt><dd>{countries.join(', ')}</dd></div>}
    </dl>
    {financing.length > 0 && <div className="offer-card-financing"><h3>Financiamiento</h3>{financing.map((text, index) => <p key={index}>{text}</p>)}</div>}
    {options.length > 1 && !offer.beneficios.some(b => b.opcion_estudio != null) && <p className="small-note">Consulta las condiciones de cada opción en el detalle.</p>}
    <div className="catalog-card-actions"><Link className="secondary-link catalog-detail-link" to={`/becas/${offer.id}`}><Icon name="detail" /><span>Ver detalle</span></Link><FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} /></div>
  </article>
}
