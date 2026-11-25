import Icon from '../components/Icon'
import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import CompactFilters from '../components/CompactFilters'
import { ADMIN_FILTER_KEYS, ADMIN_STATES } from '../components/compactFilterState'
import Message from '../components/Message'
import Button from '../components/Button'
import FavoriteButton from '../components/FavoriteButton'
import { closingText, stateLabel, providerLabel } from './offerDisplay'
import { readable } from './catalogPresentation'
import PublicCatalog from './PublicCatalog'
import { ScholarshipHeader } from '../components/ScholarshipIcon'
import { CardFact, FinancingStrip } from '../components/CardParts'
import { singleArea } from '../components/scholarshipFields'

// Datos de la tarjeta de administración con la misma presentación que el catálogo: icono, etiqueta y valor.
function AdminFacts({ offer }) {
  const active = offer.opciones.filter(option => option.activa !== false)
  const levels = [...new Set(active.map(option => option.nivel).filter(Boolean))].map(readable)
  const modes = [...new Set(active.map(option => option.modalidad).filter(Boolean))].map(readable)
  return <dl className="offer-card-facts card-facts">
    <CardFact icon="calendar" label="Cierre">{closingText(offer)}</CardFact>
    <CardFact icon="layers" label="Opciones de estudio">{active.length}</CardFact>
    <CardFact icon="explore" label={levels.length === 1 ? 'Nivel' : 'Niveles'}>{levels.join(', ') || 'No especificados'}</CardFact>
    <CardFact icon="preferences" label="Modalidades">{modes.join(', ') || 'No especificadas'}</CardFact>
    {/* El tipo solo ocupa una celda cuando tiene un valor real. */}
    {offer.tipo_beca_nombre && <CardFact icon="document" label="Tipo">{offer.tipo_beca_nombre}</CardFact>}
  </dl>
}

function PublicationReadiness({ offer }) {
  const diagnosis = offer.diagnostico
  if (!diagnosis || offer.revision === 'validada') return null
  // Franja destacada: ámbar suave si faltan pasos, verde suave si está lista.
  return <p className={`accent-note card-readiness ${diagnosis.faltan ? 'card-readiness-pending' : 'card-readiness-ready'}`}>{diagnosis.faltan ? `Faltan ${diagnosis.faltan} ${diagnosis.faltan === 1 ? 'paso' : 'pasos'} para publicar` : 'Sin pendientes: lista para revisar y publicar'}</p>
}

export default function Offers({ admin = false }) {
  return admin ? <AdministrativeOffers admin /> : <PublicCatalog />
}

function AdministrativeOffers({ admin }) {
  const [params, setParams] = useSearchParams()
  const [result, setResult] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [retry, setRetry] = useState(0)
  const query = params.toString()
  // Solo la última consulta actualiza los resultados: los de una consulta anterior no se muestran.
  const current = result?.query === query ? result : null
  const data = current?.data
  const error = current?.error || ''
  const totalPages = data ? Math.ceil(data.count / data.page_size) : 0
  // Cada cambio de filtro u orden vuelve a la primera página y se refleja en la URL; un valor vacío lo quita.
  const update = useCallback(changes => setParams(previous => {
    const next = new URLSearchParams(previous)
    next.delete('page')
    for (const [key, value] of Object.entries(changes)) {
      if (value == null || value === '') next.delete(key)
      else next.set(key, value)
    }
    return next
  }), [setParams])
  // «Limpiar todo» y «Restablecer filtros» quitan los filtros y conservan el orden.
  const clearFilters = () => update(Object.fromEntries(ADMIN_FILTER_KEYS.map(key => [key, ''])))
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get(admin ? 'gestion/convocatorias' : 'becas', Object.fromEntries(new URLSearchParams(query))), offersApi.get('becas/catalogos')])
      .then(([d, c]) => { if (live) { setResult({ query, data: d }); setCatalogs(c) } }).catch((e) => { if (live) setResult({ query, error: e.message }) })
    return () => { live = false }
  }, [query, admin, retry])
  return <OffersLayout><div className="admin-offers"><div className="page-heading"><div><p className="eyebrow">{admin ? 'ADMINISTRACIÓN' : 'EXPLORA TU PRÓXIMO PASO'}</p><h1>{admin ? 'Convocatorias' : 'Catálogo de becas'}</h1><p>Ofertas de entidades ecuatorianas · Destinos nacionales e internacionales</p></div>
    {admin && <div className="heading-actions"><Link className="secondary-link" to="/gestion/convocatorias/nueva"><Icon name="add" /><span>Crear convocatoria</span></Link><Link to="/gestion/instituciones"><Icon name="institutions" /><span>Gestionar oferentes</span></Link></div>}</div>
    {error && <><Message>{error}</Message><Button icon="refresh" onClick={() => { setResult(null); setRetry(retry + 1) }}>Reintentar</Button></>}
    {!catalogs && !error && <p role="status"><Icon name="loading" />Cargando catálogo…</p>}
    {catalogs && <CompactFilters params={params} catalogs={catalogs} onChange={update} label="Filtros de convocatorias" keys={ADMIN_FILTER_KEYS} scholarshipType states={ADMIN_STATES} />}
    {catalogs && <div className="catalog-toolbar"><p role="status" className="catalog-count">{data ? `${data.count} convocatorias encontradas` : error ? '' : <><Icon name="loading" />Cargando convocatorias…</>}</p>
      <div className="catalog-order"><label htmlFor="admin-offer-order">Ordenar por</label><select id="admin-offer-order" value={params.get('orden') || 'recientes'} onChange={e => update({ orden: e.target.value })}><option value="recientes">Recientes</option><option value="titulo">Título</option><option value="cierre">Fecha de cierre</option></select></div></div>}
    {data && <><div className="offer-grid">{data.results.map((offer) => <article className="offer-card admin-offer-card" key={offer.id}>
      <div className="card-head">
        <ScholarshipHeader field={singleArea(offer.areas, catalogs?.areas)} title={offer.titulo}>
          <p className="card-provider">{offer.institucion?.nombre || (offer.oferente_externo ? providerLabel(offer) : offer.revision === 'validada' ? 'Entidad oferente: No identificada' : 'Oferente pendiente de confirmar')}</p>{offer.origen_automatico && <p className="small-note card-origin">Borrador del rastreo · Publicación {offer.origen_automatico.publicacion_id}</p>}{offer.ficha_retirada && <p className="small-note card-origin card-retirada">La ficha oficial ya no está disponible en SIAU</p>}</ScholarshipHeader>
        <div className="card-head-status offer-card-statuses"><span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>{offer.descartado && <span className="status-pill situation-descartada">Borrador descartado</span>}</div>
      </div>
      <PublicationReadiness offer={offer} />
      <AdminFacts offer={offer} />
      <FinancingStrip items={[offer.beneficios.length ? offer.beneficios.map((b) => `${b.concepto}: ${b.porcentaje != null ? `${b.porcentaje} %` : 'porcentaje no especificado'}`).join(' · ') : offer.origen_automatico ? 'Beneficios: no publicados en la ficha' : 'Beneficios no especificados']} />
      <div className="card-foot"><div className="catalog-card-actions"><Link className="secondary-link catalog-detail-link" to={admin ? `/gestion/convocatorias/${offer.id}` : `/becas/${offer.id}`}><Icon name={admin ? "edit" : "detail"} /><span>{admin ? 'Editar y revisar' : 'Ver convocatoria'}</span></Link>
      {!admin && <FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} />}</div></div></article>)}</div>
      {data.count === 0 && <section className="profile-card"><h2>No hay convocatorias con estos filtros</h2><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button icon="clear" onClick={clearFilters}>Restablecer filtros</Button></section>}
      {totalPages > 1 && <nav className="pagination" aria-label="Paginación"><Button icon="previous" disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page} de {totalPages}</span><Button icon="next" disabled={data.page >= totalPages} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav>}</>}
    <p className="profile-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>
  </div></OffersLayout>
}
