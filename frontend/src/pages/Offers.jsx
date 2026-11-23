import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import CatalogFilters from '../components/CatalogFilters'
import Message from '../components/Message'
import Button from '../components/Button'
import FavoriteButton from '../components/FavoriteButton'
import { display, closingText, stateLabel, providerLabel } from './offerDisplay'
import { readable } from './catalogPresentation'
import PublicCatalog from './PublicCatalog'

function StudySummary({ options }) {
  const active = options.filter(option => option.activa !== false)
  const levels = [...new Set(active.map(option => option.nivel).filter(Boolean))].map(readable)
  const modes = [...new Set(active.map(option => option.modalidad).filter(Boolean))].map(readable)
  return <><p>Opciones de estudio: {active.length}</p>
    <p>{levels.length === 1 ? 'Nivel' : 'Niveles'}: {levels.join(', ') || 'No especificados'}</p>
    <p>Modalidades: {modes.join(', ') || 'No especificadas'}</p></>
}

function PublicationReadiness({ offer }) {
  const diagnosis = offer.diagnostico
  if (!diagnosis || offer.revision === 'validada') return null
  return <p className="accent-note">{diagnosis.faltan ? `Faltan ${diagnosis.faltan} ${diagnosis.faltan === 1 ? 'paso' : 'pasos'} para publicar` : 'Sin pendientes: lista para revisar y publicar'}</p>
}

export default function Offers({ admin = false }) {
  return admin ? <AdministrativeOffers admin /> : <PublicCatalog />
}

function AdministrativeOffers({ admin }) {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const query = params.toString()
  const totalPages = data ? Math.ceil(data.count / data.page_size) : 0
  const filterKeys = ['q', 'nivel', 'modalidad', 'destino', 'tipo_beca', 'estado']
  const activeFilterCount = filterKeys.filter(key => params.get(key)).length
  const applyFilters = values => {
    const next = Object.fromEntries(Object.entries(values).filter(([key, value]) => filterKeys.includes(key) && value != null && value !== ''))
    if (params.get('orden')) next.orden = params.get('orden')
    if (new URLSearchParams(next).toString() !== query) setData(null)
    setParams(next)
  }
  const clearFilters = () => { if (query) setData(null); setParams({}) }
  const orderResults = value => {
    const next = Object.fromEntries(params)
    delete next.page
    next.orden = value
    if (new URLSearchParams(next).toString() !== query) setData(null)
    setParams(next)
  }
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get(admin ? 'gestion/convocatorias' : 'becas', Object.fromEntries(new URLSearchParams(query))), offersApi.get('becas/catalogos')])
      .then(([d, c]) => { if (live) { setData(d); setCatalogs(c); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [query, admin, retry])
  return <OffersLayout><div className="admin-offers"><div className="page-heading"><div><p className="eyebrow">{admin ? 'ADMINISTRACIÓN' : 'EXPLORA TU PRÓXIMO PASO'}</p><h1>{admin ? 'Convocatorias' : 'Catálogo de becas'}</h1><p>Ofertas de entidades ecuatorianas · Destinos nacionales e internacionales</p></div>
    {admin && <div className="heading-actions"><Link className="secondary-link" to="/gestion/convocatorias/nueva"><Icon name="add" /><span>Crear convocatoria</span></Link><Link to="/gestion/instituciones"><Icon name="institutions" /><span>Gestionar oferentes</span></Link></div>}</div>
    {error && <><Message>{error}</Message><Button icon="refresh" onClick={() => setRetry(retry + 1)}>Reintentar</Button></>}
    {!catalogs && !error && <p role="status"><Icon name="loading" />Cargando catálogo…</p>}
    {catalogs && <CatalogFilters key={query} params={params} catalogs={catalogs} onApply={applyFilters} onClear={clearFilters} stateValues={['borrador', 'pausada', 'abierta', 'cerrada', 'proxima', 'sin_fecha']} activeCount={activeFilterCount} />}
    {catalogs && !data && !error && <p role="status"><Icon name="loading" />Cargando convocatorias…</p>}
    {data && <><div className="catalog-results-heading"><p role="status">{data.count} convocatorias encontradas</p><div className="field"><label htmlFor="admin-offer-order">Ordenar por</label><select id="admin-offer-order" value={params.get('orden') || 'recientes'} onChange={e => orderResults(e.target.value)}><option value="recientes">Recientes</option><option value="titulo">Título</option><option value="cierre">Fecha de cierre</option></select></div></div><div className="offer-grid">{data.results.map((offer) => <article className="offer-card" key={offer.id}>
      <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span>{offer.descartado && <span className="status-pill situation-descartada">Borrador descartado</span>}<h2>{offer.titulo}</h2><p>{offer.institucion?.nombre || (offer.oferente_externo ? providerLabel(offer) : offer.revision === 'validada' ? 'Entidad oferente: No identificada' : 'Oferente pendiente de confirmar')}</p>{offer.origen_automatico && <p className="small-note">Borrador del rastreo · Publicación {offer.origen_automatico.publicacion_id}</p>}
      <PublicationReadiness offer={offer} /><p>Tipo: {display(offer.tipo_beca_nombre)}</p>
      <p className="accent-note">{offer.beneficios.length ? offer.beneficios.map((b) => `${b.concepto}: ${b.porcentaje != null ? `${b.porcentaje} %` : 'porcentaje no especificado'}`).join(' · ') : 'Beneficios no especificados'}</p>
      <StudySummary options={offer.opciones} /><p>Cierre: {closingText(offer)}</p>
      <Link className="secondary-link" to={admin ? `/gestion/convocatorias/${offer.id}` : `/becas/${offer.id}`}><Icon name={admin ? "edit" : "detail"} /><span>{admin ? 'Editar y revisar' : 'Ver convocatoria'}</span></Link>
      {!admin && <FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} />}</article>)}</div>
      {data.count === 0 && <section className="profile-card"><h2>No hay convocatorias con estos filtros</h2><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button icon="clear" onClick={clearFilters}>Restablecer filtros</Button></section>}
      {totalPages > 1 && <nav className="pagination" aria-label="Paginación"><Button icon="previous" disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page} de {totalPages}</span><Button icon="next" disabled={data.page >= totalPages} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav>}</>}
    <p className="profile-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>
  </div></OffersLayout>
}
