import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Message from '../components/Message'

export default function Notifications() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const key = `${page}-${revision}`
  useEffect(() => {
    let live = true
    offersApi.get('notificaciones', { page }).then((data) => {
      if (!live) return
      if (page > 1 && !data.results.length) { setPage(page - 1); return }
      setResult({ key, data })
    }).catch((failure) => { if (live) setResult({ key, error: failure.message }) })
    return () => { live = false }
  }, [key, page])

  const current = result?.key === key ? result : null
  async function mark(item) {
    if (busy) return
    setBusy(item.id)
    setError('')
    try {
      const response = await offersApi.write(`notificaciones/${item.id}/leer`, 'POST', {})
      setResult((previous) => previous?.data ? { ...previous, data: {
        ...previous.data, no_leidas: Math.max(0, previous.data.no_leidas - 1),
        results: previous.data.results.map((row) => row.id === item.id ? { ...row, leida_en: response.leida_en } : row),
      } } : previous)
      window.dispatchEvent(new Event('becanexo:notificaciones'))
    } catch (failure) { setError(failure.message) }
    finally { setBusy(null) }
  }

  return <OffersLayout><div className="page-heading"><div><p className="eyebrow">TUS AVISOS</p><h1>Notificaciones</h1><p>Convocatorias publicadas relacionadas con información que declaraste. Revisa siempre sus requisitos y bases oficiales.</p></div></div>
    {!current && <p role="status"><Icon name="loading" />Cargando notificaciones…</p>}
    {current?.error && <><Message>{current.error}</Message><Button icon="refresh" onClick={() => setRevision((value) => value + 1)}>Reintentar</Button></>}
    <Message>{error}</Message>
    {current?.data && <><p className="results-count">{current.data.no_leidas} sin leer · {current.data.count} en total</p>
      {!current.data.count ? <section className="profile-card"><h2>Aún no tienes notificaciones</h2><p>Cuando se publique una convocatoria relacionada con tus datos declarados, aparecerá aquí.</p></section> :
        <ul className="notification-list">{current.data.results.map((item) => <li className={`profile-card notification-item${item.leida_en ? ' notification-read' : ''}`} key={item.id}>
          <div><span className="small-note">{item.leida_en ? 'Leída' : 'Sin leer'}</span><h2>{item.titulo}</h2><p>Relacionado con: {item.motivos.join(', ')}. La coincidencia no confirma todos los requisitos ni la adjudicación.</p><p className="small-note">Recibida: {new Date(item.creada_en).toLocaleDateString('es-EC')}</p></div>
          <div className="notification-actions">{item.disponible ? <Link className="secondary-link" to={`/becas/${item.convocatoria_id}`}><Icon name="detail" /><span>Ver beca</span></Link> : <span className="small-note">La convocatoria ya no está disponible públicamente.</span>}
            {!item.leida_en && <Button icon="success" busy={busy === item.id} disabled={busy !== null} onClick={() => mark(item)}>Marcar como leída</Button>}</div>
        </li>)}</ul>}
      {current.data.count > current.data.page_size && <nav className="pagination" aria-label="Paginación de notificaciones"><Button icon="previous" disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button icon="next" disabled={page * current.data.page_size >= current.data.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}
    </>}
  </OffersLayout>
}
