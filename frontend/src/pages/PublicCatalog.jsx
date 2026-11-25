import Icon from '../components/Icon'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import CompactFilters from '../components/CompactFilters'
import { PUBLIC_FILTER_KEYS } from '../components/compactFilterState'
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
  // Los estados que antes se elegían en «Más filtros» siguen funcionando por URL y marcan la pestaña que los contiene.
  const activeView = { abierta: 'vigentes', cierre_hoy: 'vigentes', sin_fecha: 'todas' }[params.get('estado')] || params.get('estado') || 'vigentes'
  // Cada cambio de filtro, pestaña u orden vuelve a la primera página y se refleja en la URL; un valor vacío lo quita.
  const update = useCallback(changes => setParams(previous => {
    const next = new URLSearchParams(previous)
    next.delete('page')
    for (const [key, value] of Object.entries(changes)) {
      if (value == null || value === '') next.delete(key)
      else next.set(key, value)
    }
    return next
  }), [setParams])
  const changeView = view => update({ estado: view === 'vigentes' ? '' : view })
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
    // Solo la última consulta actualiza el resultado: las respuestas de consultas anteriores se descartan.
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
  // Las opciones de los selectores usan las últimas facetas recibidas mientras llega la consulta nueva.
  const facets = result?.data?.facetas
  const currentRecommendations = recommendations?.userId === userId && recommendations?.retry === recommendationsRetry ? recommendations : null
  // Por defecto el servidor muestra solo becas con entidad oferente ecuatoriana; el interruptor incluye las demás.
  const includesOthers = params.get('incluir_no_ecuatorianas') === '1'
  const hasActiveFilters = PUBLIC_FILTER_KEYS.filter(key => key !== 'incluir_no_ecuatorianas').some(key => Boolean(params.get(key)))
  // «Limpiar todo» quita los filtros y conserva la pestaña de vigencia y el orden.
  const clear = () => update(Object.fromEntries(PUBLIC_FILTER_KEYS.map(key => [key, ''])))
  const retryCatalogs = () => { setCatalogError(''); setCatalogRetry(value => value + 1) }
  const loading = (!current || (!catalogs && !catalogError)) && !current?.error
  return <OffersLayout><div className="public-catalog"><div className="page-heading"><div><p className="eyebrow">EXPLORA TU PRÓXIMO PASO</p><h1>Catálogo de becas</h1><p>Oportunidades pertinentes para Ecuador · Consulta la procedencia de cada beca</p></div></div>
    {userId != null && <div className="catalog-modes" role="group" aria-label="Modo de resultados">
      <Button type="button" className={activeMode === 'all' ? 'catalog-mode-active' : 'button-light'} aria-pressed={activeMode === 'all'} onClick={() => setMode('all')}>Todas las becas</Button>
      <Button type="button" className={activeMode === 'ia' ? 'catalog-mode-active' : 'button-light'} aria-pressed={activeMode === 'ia'} onClick={() => setMode('ia')}>Para ti · IA</Button>
    </div>}
    <div className="catalog-results">
    {activeMode === 'all' ? <>
    {catalogs && <CompactFilters params={params} catalogs={catalogs} facets={facets} onChange={update} quickDestination providerToggle />}
    <div className="catalog-toolbar">
      <div className="catalog-modes" role="group" aria-label="Vigencia de las becas">
        {[["vigentes", "Vigentes"], ["proxima", "Próximas"], ["cerrada", "Cerradas"], ["todas", "Todas las publicadas"]].map(([value, label]) => <Button key={value} type="button" className={activeView === value ? 'catalog-mode-active' : 'button-light'} aria-pressed={activeView === value} onClick={() => changeView(value)}>{label}</Button>)}
      </div>
      <div className="catalog-toolbar-end">
        <p role="status" className="catalog-count">{loading ? <><Icon name="loading" />Cargando catálogo…</> : data && catalogs ? `${data.count} ${data.count === 1 ? 'convocatoria encontrada' : 'convocatorias encontradas'}` : ''}</p>
        <div className="catalog-order"><label htmlFor="catalog-order">Ordenar por</label><select id="catalog-order" aria-describedby="catalog-order-hint" value={params.get('orden') || 'recientes'} onChange={e => update({ orden: e.target.value })}><option value="recientes">Recientes</option><option value="titulo">Título</option><option value="cierre">Fecha de cierre</option></select><small id="catalog-order-hint" className="visually-hidden">Se aplica al seleccionar.</small></div>
      </div>
    </div>
    {current?.error && <><Message>{current.error}</Message><Button icon="refresh" onClick={() => { setResult(null); setRetry(retry + 1) }}>Reintentar</Button></>}
    {!catalogs && catalogError && <><Message>{catalogError}</Message><Button icon="refresh" onClick={retryCatalogs}>Reintentar datos del catálogo</Button></>}
    {data && catalogs && <>
      <div className="offer-grid">{data.results.map(offer => <CatalogCard key={offer.id} offer={offer} catalogs={catalogs} />)}</div>
      {data.count === 0 && (includesOthers ? <section className="profile-card"><h2>{hasActiveFilters ? 'No encontramos becas que coincidan con los filtros seleccionados' : 'No hay convocatorias disponibles actualmente'}</h2>{hasActiveFilters && <><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button icon="clear" onClick={clear}>Restablecer filtros</Button></>}</section>
        : <section className="profile-card"><h2>No hay becas de entidades ecuatorianas con estos filtros.</h2><p>Puedes incluir becas de entidades no ecuatorianas o sin confirmar.</p>{hasActiveFilters && <Button icon="clear" onClick={clear}>Restablecer filtros</Button>}</section>)}
      {data.count > data.page_size && <nav className="pagination" aria-label="Paginación"><Button icon="previous" disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page}</span><Button icon="next" disabled={data.page * data.page_size >= data.count} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav>}
      {data.results.some(o => o.beneficios.some(b => b.porcentaje != null)) && <p className="profile-note catalog-coverage-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>}
    </>}
    </> : <Recommendations catalogs={catalogs} state={currentRecommendations} onRefresh={() => setRecommendationsRetry(value => value + 1)} catalogError={catalogError} onRetryCatalog={retryCatalogs} />}
    </div>
  </div></OffersLayout>
}
