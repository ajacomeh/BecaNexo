import Icon from '../components/Icon'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import CatalogFilters from '../components/CatalogFilters'
import CatalogCard from '../components/CatalogCard'
import Button from '../components/Button'
import Message from '../components/Message'
import Recommendations from '../components/Recommendations'
import { useAuth } from '../auth/context'

export default function PublicCatalog() {
  const { user } = useAuth()
  return <CatalogBody key={user?.id ?? 'anonymous'} user={user} />
}

function CatalogBody({ user }) {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [result, setResult] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [catalogError, setCatalogError] = useState('')
  const [catalogRetry, setCatalogRetry] = useState(0)
  const [retry, setRetry] = useState(0)
  const [mode, setMode] = useState('all')
  const [recommendations, setRecommendations] = useState(null)
  const [recommendationsRetry, setRecommendationsRetry] = useState(0)
  const recommendationsCache = useRef(null)
  const userId = user?.rol === 'postulante' ? user.id : null
  const activeMode = userId == null ? 'all' : mode
  useEffect(() => {
    if (activeMode !== 'ia') return
    const cached = recommendationsCache.current
    if (cached?.userId === userId && cached.retry === recommendationsRetry) return
    let live = true
    offersApi.get('becas/recomendaciones').then(data => {
      if (!live) return
      const result = { userId, retry: recommendationsRetry, data, error: '' }
      recommendationsCache.current = result
      setRecommendations(result)
    }).catch(error => {
      if (live) setRecommendations({ userId, retry: recommendationsRetry, data: null, error: error.message })
    })
    return () => { live = false }
  }, [activeMode, userId, recommendationsRetry])
  useEffect(() => {
    let live = true
    offersApi.get('becas', Object.fromEntries(new URLSearchParams(query))).then(data => {
      if (live) setResult({ query, data })
    }).catch(e => { if (live) setResult({ query, error: e.message }) })
    return () => { live = false }
  }, [query, retry])
  useEffect(() => {
    let live = true
    offersApi.get('becas/catalogos').then(data => {
      if (live) { setCatalogs(data); setCatalogError('') }
    }).catch(error => { if (live) setCatalogError(error.message) })
    return () => { live = false }
  }, [catalogRetry])
  const current = result?.query === query ? result : null
  const data = current?.data
  const currentRecommendations = recommendations?.userId === userId && recommendations?.retry === recommendationsRetry ? recommendations : null
  const hasActiveFilters = ['q', 'nivel', 'modalidad', 'destino', 'tipo_beca', 'estado'].some(key => Boolean(params.get(key)))
  const clear = () => { setParams({}) }
  const retryCatalogs = () => { setCatalogError(''); setCatalogRetry(value => value + 1) }
  const apply = values => setParams(Object.fromEntries(Object.entries(values).filter(([k, v]) => ['q', 'nivel', 'modalidad', 'destino', 'tipo_beca', 'estado', 'orden', 'page_size'].includes(k) && v != null && v !== '')))
  return <OffersLayout><div className="public-catalog"><div className="page-heading"><div><p className="eyebrow">EXPLORA TU PRÓXIMO PASO</p><h1>Catálogo de becas</h1><p>Ofertas de entidades ecuatorianas · Destinos nacionales e internacionales</p></div></div>
    {userId != null && <div className="catalog-modes" role="group" aria-label="Modo de resultados">
      <Button type="button" className={activeMode === 'all' ? 'catalog-mode-active' : 'button-light'} aria-pressed={activeMode === 'all'} onClick={() => setMode('all')}>Todas las becas</Button>
      <Button type="button" className={activeMode === 'ia' ? 'catalog-mode-active' : 'button-light'} aria-pressed={activeMode === 'ia'} onClick={() => setMode('ia')}>Para ti · IA</Button>
    </div>}
    <div className="catalog-results">
    {activeMode === 'all' ? <>
    {catalogs && <CatalogFilters key={query} params={params} catalogs={catalogs} onApply={apply} onClear={clear} />}
    {(!current || (!catalogs && !catalogError)) && !current?.error && <p role="status"><Icon name="loading" />Cargando catálogo…</p>}
    {current?.error && <><Message>{current.error}</Message><Button icon="refresh" onClick={() => { setResult(null); setRetry(retry + 1) }}>Reintentar</Button></>}
    {!catalogs && catalogError && <><Message>{catalogError}</Message><Button icon="refresh" onClick={retryCatalogs}>Reintentar datos del catálogo</Button></>}
    {data && catalogs && <><div className="catalog-results-heading"><p role="status">{data.count} {data.count === 1 ? 'convocatoria encontrada' : 'convocatorias encontradas'}</p><div className="field"><label htmlFor="catalog-order">Ordenar por</label><select id="catalog-order" aria-describedby="catalog-order-hint" value={params.get('orden') || 'recientes'} onChange={e => apply({ ...Object.fromEntries(params), orden: e.target.value })}><option value="recientes">Recientes</option><option value="titulo">Título</option><option value="cierre">Fecha de cierre</option></select><small id="catalog-order-hint">Se aplica al seleccionar.</small></div></div>
      <div className="offer-grid">{data.results.map(offer => <CatalogCard key={offer.id} offer={offer} catalogs={catalogs} />)}</div>
      {data.count === 0 && <section className="profile-card"><h2>{hasActiveFilters ? 'No encontramos becas que coincidan con los filtros seleccionados' : 'No hay convocatorias disponibles actualmente'}</h2>{hasActiveFilters && <><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button icon="clear" onClick={clear}>Restablecer filtros</Button></>}</section>}
      {data.count > data.page_size && <nav className="pagination" aria-label="Paginación"><Button icon="previous" disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page}</span><Button icon="next" disabled={data.page * data.page_size >= data.count} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav>}
      {data.results.some(o => o.beneficios.some(b => b.porcentaje != null)) && <p className="profile-note catalog-coverage-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>}
    </>}
    </> : <Recommendations catalogs={catalogs} state={currentRecommendations} onRefresh={() => setRecommendationsRetry(value => value + 1)} catalogError={catalogError} onRetryCatalog={retryCatalogs} />}
    </div>
  </div></OffersLayout>
}
