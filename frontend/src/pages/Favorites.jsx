import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import FavoriteButton from '../components/FavoriteButton'
import Button from '../components/Button'
import Message from '../components/Message'
import { date, display, stateLabel } from './offerDisplay'

export default function Favorites() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState(null)
  const key = `${page}-${revision}`
  useEffect(() => {
    let live = true
    offersApi.get('favoritos', { page }).then((data) => {
      if (!live) return
      if (page > 1 && !data.results.length) { setPage(page - 1); return }
      setResult({ key, data })
    }).catch((e) => { if (live) setResult({ key, error: e.message }) })
    return () => { live = false }
  }, [key, page])
  const current = result?.key === key ? result : null
  return <OffersLayout><div className="page-heading"><div><p className="eyebrow">TUS OPORTUNIDADES GUARDADAS</p><h1>Mis becas favoritas</h1><p>Conserva las ofertas que te interesan para consultarlas después.</p></div><Link className="secondary-link" to="/becas">Explorar becas</Link></div>
    {!current && <p role="status">Cargando favoritos…</p>}
    {current?.error && <><Message>{current.error}</Message><Button onClick={() => setRevision(revision + 1)}>Reintentar</Button></>}
    {current?.data && <>{!current.data.count ? <section className="profile-card"><h2>Aún no tienes favoritos</h2><p>Guarda una oportunidad desde el catálogo o su detalle.</p></section> : <div className="offer-grid">{current.data.results.map((favorite) => <article className="offer-card" key={favorite.id}>
      {favorite.disponible ? <><span className={`status-pill state-${favorite.convocatoria.estado}`}>{stateLabel(favorite.convocatoria.estado)}</span><h2>{favorite.convocatoria.titulo}</h2><p>{favorite.convocatoria.institucion}</p><p>Tipo: {display(favorite.convocatoria.tipo_beca)}</p><p>Cierre: {date(favorite.convocatoria.cierre)}</p><Link className="secondary-link" to={`/becas/${favorite.convocatoria.id}`}>Ver convocatoria</Link></> : <h2>{favorite.aviso}</h2>}
      <FavoriteButton initialId={favorite.id} onRemoved={() => setRevision((v) => v + 1)} />
    </article>)}</div>}
    {current.data.count > 0 && <nav className="pagination" aria-label="Paginación"><Button disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={page * current.data.page_size >= current.data.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</>}
  </OffersLayout>
}
