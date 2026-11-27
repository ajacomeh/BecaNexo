import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'
import { ScholarshipTitle } from './ScholarshipIcon'
import { offersApi } from '../api/client'
import { providerLabel, stateLabel } from '../pages/offerDisplay'
import { readable } from '../pages/catalogPresentation'

// «Becas similares» del detalle: es un complemento, así que si no hay resultados o la consulta falla, no se muestra.
export default function SimilarOffers({ offerId }) {
  const [state, setState] = useState({ loading: true, results: [] })
  useEffect(() => {
    let live = true
    offersApi.get(`becas/${offerId}/similares`)
      .then((data) => { if (live) setState({ loading: false, results: data.results || [] }) })
      .catch(() => { if (live) setState({ loading: false, results: [] }) })
    return () => { live = false }
  }, [offerId])
  if (!state.loading && !state.results.length) return null
  return <section className="profile-card offer-detail-section" aria-labelledby="becas-similares-titulo">
    <h2 id="becas-similares-titulo">Becas similares</h2>
    <p className="small-note">Becas parecidas por su contenido, calculadas con un modelo de IA local. No indican que cumplas sus requisitos.</p>
    {state.loading ? <p role="status"><Icon name="loading" />Buscando becas similares…</p>
      : <div className="offer-grid" role="list" aria-label="Becas similares">{state.results.map((item) => <article className="offer-card favorite-card" role="listitem" key={item.id}>
        <div className="offer-card-heading"><span className={`status-pill state-${item.estado}`}>{stateLabel(item.estado)}</span>
          <ScholarshipTitle as="h3" field={item.campo_conocimiento}>{item.titulo}</ScholarshipTitle>
          <p className="offer-provider">{providerLabel(item)}</p></div>
        {item.niveles?.length > 0 && <dl className="offer-card-facts"><div><dt>{item.niveles.length === 1 ? 'Nivel' : 'Niveles'}</dt><dd>{item.niveles.map(readable).join(', ')}</dd></div></dl>}
        <div className="catalog-card-actions"><Link className="secondary-link" to={`/becas/${item.id}`} aria-label={`Ver detalle: ${item.titulo}`}
          onClick={() => window.scrollTo?.(0, 0)}><Icon name="detail" /><span>Ver detalle</span></Link></div>
      </article>)}</div>}
  </section>
}
