import Icon from './Icon'
import { Link } from 'react-router-dom'
import FavoriteButton from './FavoriteButton'
import { stateLabel, closingText, providerLabel } from '../pages/offerDisplay'

import { readable, benefitSummary, unique } from '../pages/catalogPresentation'
import { ScholarshipHeader } from './ScholarshipIcon'
import { CardFact, FinancingStrip } from './CardParts'
import { singleArea } from './scholarshipFields'

// Estado de requisitos de una recomendación: mismo texto de siempre, con color e ícono como en la comparación.
const requirementStates = {
  cumple: ['Requisitos declarados: coinciden', 'success'],
  no_cumple: ['Requisitos: no cumple', 'failure'],
  desconocido: ['Requisitos: información pendiente', 'pending'],
}

export default function CatalogCard({ offer, catalogs, recommendation }) {
  const [requirementLabel, requirementIcon] = recommendation ? requirementStates[recommendation.elegibilidad] || requirementStates.desconocido : []
  const requirementState = recommendation && requirementStates[recommendation.elegibilidad] ? recommendation.elegibilidad : 'desconocido'
  const options = offer.opciones
  const destinations = unique(options.flatMap(o => o.paises || []))
  const countries = destinations.map(id => catalogs.paises.find(p => p.id === id)?.nombre).filter(Boolean)
  const financing = benefitSummary(offer.beneficios)
  const statuses = recommendation ? <div className="offer-card-statuses">{offer.estado !== 'sin_fecha' && <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>}<span className={`status-pill recommendation-status recommendation-status-${requirementState}`} role="img" aria-label={requirementLabel}><Icon name={requirementIcon} /><span>{requirementLabel}</span></span></div> : <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>
  return <article className="offer-card catalog-card">
    {/* Cabecera: icono y título a la izquierda, estado arriba a la derecha y la entidad debajo del título. */}
    <div className="offer-card-heading card-head">
      <ScholarshipHeader field={singleArea(offer.areas, catalogs?.areas)} title={offer.titulo}><p className="offer-provider card-provider">{providerLabel(offer)}</p></ScholarshipHeader>
      <div className="card-head-status">{statuses}</div>
    </div>
    <dl className="offer-card-facts card-facts"><CardFact icon="calendar" label="Cierre">{closingText(offer, true)}</CardFact>
      {options.length === 1 && <CardFact icon="layers" label="Nivel y modalidad">{readable(options[0].nivel)} · {readable(options[0].modalidad)}</CardFact>}
      {options.length > 1 && <CardFact icon="layers" label="Opciones de estudio">{options.length} · {unique(options.map(o => readable(o.nivel))).join(', ')} · {unique(options.map(o => readable(o.modalidad))).join(', ')}</CardFact>}
      {countries.length > 0 && <CardFact icon="location" label={countries.length === 1 ? 'Destino' : 'Destinos'}>{countries.join(', ')}</CardFact>}
    </dl>
    {financing.length > 0 && <FinancingStrip items={financing} />}
    {recommendation && <div className="recommendation-explanation"><p className={`recommendation-requirements recommendation-requirements-${requirementState}`}><strong><Icon name={requirementIcon} />Requisitos</strong><span>{recommendation.requirements}</span></p><p><strong>Afinidad temática</strong><span>{recommendation.affinity}</span></p><p><strong>Preferencias</strong><span>{recommendation.preferences}</span></p></div>}
    {/* Pie al fondo: los botones de tarjetas de una misma fila quedan a la misma altura. */}
    <div className="card-foot">
      {options.length > 1 && !offer.beneficios.some(b => b.opcion_estudio != null) && <p className="small-note">Consulta las condiciones de cada opción en el detalle.</p>}
      <div className="catalog-card-actions"><Link className="secondary-link catalog-detail-link" to={`/becas/${offer.id}`}><Icon name="detail" /><span>Ver detalle</span></Link><FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} /></div>
    </div>
  </article>
}
