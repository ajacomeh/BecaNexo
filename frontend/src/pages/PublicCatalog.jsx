import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import CatalogFilters from '../components/CatalogFilters'
import CatalogCard from '../components/CatalogCard'
import Button from '../components/Button'
import Message from '../components/Message'

export default function PublicCatalog() {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [result, setResult] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get('becas', Object.fromEntries(new URLSearchParams(query))), offersApi.get('becas/catalogos')]).then(([data, c]) => {
      if (live) { setResult({ query, data }); setCatalogs(c) }
    }).catch(e => { if (live) setResult({ query, error: e.message }) })
    return () => { live = false }
  }, [query, retry])
  const current = result?.query === query ? result : null
  const data = current?.data
  const clear = () => { setParams({}) }
  const apply = values => setParams(Object.fromEntries(Object.entries(values).filter(([k, v]) => ['q', 'nivel', 'modalidad', 'destino', 'tipo_beca', 'estado', 'orden', 'page_size'].includes(k) && v != null && v !== '')))
  return <OffersLayout><div className="public-catalog"><div className="page-heading"><div><p className="eyebrow">EXPLORA TU PRÓXIMO PASO</p><h1>Catálogo de becas</h1><p>Ofertas de entidades ecuatorianas · Destinos nacionales e internacionales</p></div></div>
    {catalogs && <CatalogFilters key={query} params={params} catalogs={catalogs} onApply={apply} onClear={clear} />}
    {!current && <p role="status">Cargando catálogo…</p>}
    {current?.error && <><Message>{current.error}</Message><Button onClick={() => { setResult(null); setRetry(retry + 1) }}>Reintentar</Button></>}
    {data && <><div className="catalog-results-heading"><p role="status">{data.count} {data.count === 1 ? 'convocatoria encontrada' : 'convocatorias encontradas'}</p><div className="field"><label htmlFor="catalog-order">Ordenar por</label><select id="catalog-order" aria-describedby="catalog-order-hint" value={params.get('orden') || 'recientes'} onChange={e => apply({ ...Object.fromEntries(params), orden: e.target.value })}><option value="recientes">Recientes</option><option value="titulo">Título</option><option value="cierre">Fecha de cierre</option></select><small id="catalog-order-hint">Se aplica al seleccionar.</small></div></div>
      <div className="offer-grid">{data.results.map(offer => <CatalogCard key={offer.id} offer={offer} catalogs={catalogs} />)}</div>
      {data.count === 0 && <section className="profile-card"><h2>No hay convocatorias con estos filtros</h2><p>Puedes cambiar la búsqueda o restablecer los filtros.</p><Button onClick={clear}>Restablecer filtros</Button></section>}
      {data.count > data.page_size && <nav className="pagination" aria-label="Paginación"><Button disabled={data.page <= 1} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page - 1 })}>Anterior</Button><span>Página {data.page}</span><Button disabled={data.page * data.page_size >= data.count} onClick={() => setParams({ ...Object.fromEntries(params), page: data.page + 1 })}>Siguiente</Button></nav>}
      {data.results.some(o => o.beneficios.some(b => b.porcentaje != null)) && <p className="profile-note catalog-coverage-note">Los porcentajes corresponden al concepto indicado, no al costo total. Revisa las condiciones de cada opción.</p>}
    </>}
  </div></OffersLayout>
}
