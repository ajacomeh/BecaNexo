import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import FavoriteButton from '../components/FavoriteButton'
import Button from '../components/Button'
import Message from '../components/Message'
import { display, stateLabel, closingText } from './offerDisplay'

export default function Favorites() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState(null)
  const key = `${page}-${revision}`
  useEffect(() => {
    let live = true
    offersApi.get('favoritos', { page }).then((data) => {
      if (!live) return
      const lastPage = Math.max(1, Math.ceil(data.count / data.page_size))
      if (page > lastPage) { setPage(lastPage); return }
      setResult({ key, data })
    }).catch((e) => { if (live) setResult({ key, error: e.message }) })
    return () => { live = false }
  }, [key, page])
  const current = result?.key === key ? result : null
  const totalPages = current?.data?.page_size ? Math.ceil(current.data.count / current.data.page_size) : 0
  return <OffersLayout><div className="page-heading"><div><p className="eyebrow">TUS OPORTUNIDADES GUARDADAS</p><h1>Mis becas favoritas</h1><p>Conserva las ofertas que te interesan para consultarlas después.</p></div><Link className="secondary-link" to="/becas"><Icon name="explore" /><span>Explorar becas</span></Link></div>
    {!current && <p role="status"><Icon name="loading" />Cargando favoritos…</p>}
    {current?.error && <><Message>{current.error}</Message><Button icon="refresh" onClick={() => setRevision(revision + 1)}>Reintentar</Button></>}
    {current?.data && <>{!current.data.count ? <section className="profile-card"><h2>Aún no tienes favoritos</h2><p>Guarda una oportunidad desde el catálogo o su detalle.</p></section> : <div className="offer-grid">{current.data.results.map((favorite) => <article className="offer-card favorite-card" key={favorite.id}>
      {favorite.disponible ? <><div className="offer-card-heading"><span className={`status-pill state-${favorite.convocatoria.estado}`}>{stateLabel(favorite.convocatoria.estado)}</span><h2>{favorite.convocatoria.titulo}</h2><p className="offer-provider">{favorite.convocatoria.institucion}</p></div><dl className="offer-card-facts"><div><dt>Cierre</dt><dd>{favorite.convocatoria.cierre ? closingText(favorite.convocatoria) : 'Consulta el detalle para confirmar el cierre'}</dd></div><div><dt>Tipo de beca</dt><dd>{display(favorite.convocatoria.tipo_beca)}</dd></div></dl><div className="catalog-card-actions"><Link className="secondary-link" to={`/becas/${favorite.convocatoria.id}`}><Icon name="detail" /><span>Ver convocatoria</span></Link><FavoriteButton initialId={favorite.id} onRemoved={() => setRevision((v) => v + 1)} /></div></> : <><h2>{favorite.aviso}</h2><FavoriteButton initialId={favorite.id} onRemoved={() => setRevision((v) => v + 1)} /></>}
    </article>)}</div>}
    {totalPages > 1 && <nav className="pagination" aria-label="Paginación"><Button icon="previous" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page} de {totalPages}</span><Button icon="next" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</>}
  </OffersLayout>
}
