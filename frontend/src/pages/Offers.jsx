import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import OfferForm from '../components/OfferForm'
import Message from '../components/Message'
import Button from '../components/Button'
import FavoriteButton from '../components/FavoriteButton'
import { choices, enumOptions } from './offerFields'
import { display, date, stateLabel } from './offerDisplay'

export default function Offers({ admin = false }) {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const query = params.toString()
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get(admin ? 'gestion/convocatorias' : 'becas', Object.fromEntries(new URLSearchParams(query))), offersApi.get('becas/catalogos')])
      .then(([d, c]) => { if (live) { setData(d); setCatalogs(c); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [query, admin, retry])
  const filters = catalogs && [{ name: 'q', label: 'Buscar título, institución o área' },
    { name: 'nivel', label: 'Nivel', options: choices(catalogs.niveles, 'valor') }, { name: 'modalidad', label: 'Modalidad', options: choices(catalogs.modalidades, 'valor') },
    { name: 'destino', label: 'Destino de estudio', options: choices(catalogs.paises, 'codigo') }, { name: 'tipo_beca', label: 'Tipo de beca', options: choices(catalogs.tipos_beca) },
    { name: 'estado', label: 'Estado', options: enumOptions(admin ? ['borrador', 'pausada', 'abierta', 'cerrada', 'proxima', 'sin_fecha'] : ['abierta', 'cerrada', 'proxima', 'sin_fecha']) },
    { name: 'orden', label: 'Ordenar por', options: enumOptions(['recientes', 'titulo', 'cierre']) }]
  return <OffersLayout><div className="page-heading"><div><p className="eyebrow">{admin ? 'ADMINISTRACIÓN' : 'EXPLORA TU PRÓXIMO PASO'}</p><h1>{admin ? 'Convocatorias' : 'Catálogo de becas'}</h1><p>Ofertas de entidades ecuatorianas · Destinos nacionales e internacionales</p></div>
    {admin && <div className="form-actions"><Link className="secondary-link" to="/gestion/convocatorias/nueva">Crear convocatoria</Link><Link to="/gestion/instituciones">Gestionar oferentes</Link></div>}</div>
    {error && <><Message>{error}</Message><Button onClick={() => setRetry(retry + 1)}>Reintentar</Button></>}
    {!catalogs && !error && <p role="status">Cargando catálogo…</p>}
    {filters && <section className="profile-card"><h2>Filtros de búsqueda</h2><OfferForm key={query} fields={filters} initial={Object.fromEntries(params)} label="Aplicar filtros" onSubmit={async (values) => { setData(null); setParams(Object.fromEntries(Object.entries(values).filter(([, v]) => v != null && v !== ''))) }} /></section>}
    {data && <><p className="results-count">{data.count} convocatorias encontradas</p><div className="offer-grid">{data.results.map((offer) => <article className="offer-card" key={offer.id}>
      <span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span><h2>{offer.titulo}</h2><p>{offer.institucion.nombre}</p><p>Tipo: {display(offer.tipo_beca_nombre)}</p>
      <p className="accent-note">{offer.beneficios.length ? offer.beneficios.map((b) => `${b.concepto}: ${b.porcentaje != null ? `${b.porcentaje} %` : 'porcentaje no especificado'}`).join(' · ') : 'Beneficios no especificados'}</p>
      <p>{offer.opciones.map((o) => `${o.nivel} / ${o.modalidad}`).join(' · ') || 'Opciones no especificadas'}</p><p>Cierre: {date(offer.cierre)}</p>
      <Link className="secondary-link" to={admin ? `/gestion/convocatorias/${offer.id}` : `/becas/${offer.id}`}>{admin ? 'Editar y revisar' : 'Ver convocatoria'}</Link>
      {!admin && <FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} />}</article>)}</div>
      {data.count === 0 && <section className="profile-card"><h2>No hay convocatorias con estos filtros</h2><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button onClick={() => setParams({})}>Restablecer filtros</Button></section>}
      <nav className="pagination" aria-label="Paginación"><Button disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page}</span><Button disabled={data.page * data.page_size >= data.count} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav></>}
    <p className="profile-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>
  </OffersLayout>
}
