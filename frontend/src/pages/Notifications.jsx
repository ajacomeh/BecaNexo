import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Message from '../components/Message'
import { ScholarshipTitle } from '../components/ScholarshipIcon'

export default function Notifications() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [mailPreference, setMailPreference] = useState(null)
  const [mailError, setMailError] = useState('')
  const [mailBusy, setMailBusy] = useState(false)
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
  useEffect(() => {
    let live = true
    offersApi.get('notificaciones/correo').then((value) => {
      if (live) setMailPreference(value)
    }).catch(() => { if (live) setMailError('No se pudo consultar la preferencia de correo.') })
    return () => { live = false }
  }, [])

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

  async function changeMail(enabled) {
    if (mailBusy || !mailPreference?.disponible) return
    setMailBusy(true); setMailError('')
    try {
      const result = await offersApi.write('notificaciones/correo', 'PATCH', { habilitado: enabled })
      setMailPreference(result)
    } catch { setMailError('No se pudo guardar la preferencia de correo.') }
    finally { setMailBusy(false) }
  }

  function card(item) {
    const fecha = new Date(item.creada_en).toLocaleDateString('es-EC')
    return <li className={`profile-card notification-item${item.leida_en ? ' notification-read' : ' notification-unread'}`} key={item.id}>
      <div className="notification-content">
        <ScholarshipTitle as="h3" field={item.campo_conocimiento}>{item.titulo}</ScholarshipTitle>
        <div className="notification-meta"><span className={`notification-state${item.leida_en ? ' notification-state-read' : ''}`}>{item.leida_en ? 'Leída' : 'Sin leer'}</span><span className="notification-date">Recibida: {fecha}</span></div>
        {item.tipo === 'cierre_proximo'
          ? <div className="notification-reason"><span className="notification-reason-label">Cierre próximo:</span><span>{item.cierre_texto ? `Esta beca de tus favoritas ${item.cierre_texto}.` : 'Esta beca de tus favoritas está por cerrar.'}</span></div>
          : <div className="notification-reason"><span className="notification-reason-label">Coincidencia:</span><ul className="notification-chips" aria-label="Motivos de la coincidencia">{item.motivos.map((motivo) => <li key={motivo}>{motivo}</li>)}</ul></div>}
        <div className="notification-actions">{item.disponible
          ? <Link className="button notification-primary" to={`/becas/${item.convocatoria_id}`} aria-label={`Ver beca: ${item.titulo}`}><Icon name="detail" /><span>Ver beca</span></Link>
          : <span className="small-note">La convocatoria ya no está disponible públicamente.</span>}
          {!item.leida_en && <Button icon="success" className="button-light notification-secondary" busy={busy === item.id} disabled={busy !== null}
            aria-label={`Marcar como leída: ${item.titulo}`} onClick={() => mark(item)}>Marcar como leída</Button>}</div>
      </div>
    </li>
  }
  const groups = current?.data ? [['sin-leer', 'Sin leer', current.data.results.filter((item) => !item.leida_en)],
    ['leidas', 'Leídas', current.data.results.filter((item) => item.leida_en)]] : []

  return <OffersLayout><div className="page-heading"><div><p className="eyebrow">TUS AVISOS</p><h1>Notificaciones</h1><p>Becas relacionadas con tu perfil y avisos de cierre de tus favoritas. Revisa siempre los requisitos y las bases oficiales.</p>
    <p className="small-note notification-disclaimer"><Icon name="info" /><span>La coincidencia no confirma todos los requisitos ni la adjudicación.</span></p></div></div>
    <section className="mail-settings" aria-label="Avisos por correo"><div className="mail-settings-row"><div className="mail-settings-copy"><Icon name="mail" /><div><h2>Avisos por correo</h2><p className="small-note">Si lo activas, te enviamos al correo de tu cuenta cada aviso nuevo: becas publicadas relacionadas con tu perfil y cierres próximos de tus favoritas. Los avisos anteriores a la activación no se envían. Puedes desactivarlo cuando quieras; tus avisos seguirán aquí.</p></div></div>
      {mailPreference ? <label className="mail-switch"><input type="checkbox" role="switch" aria-label="Recibir avisos por correo" checked={Boolean(mailPreference.habilitado)} disabled={!mailPreference.disponible || mailBusy} onChange={(event) => changeMail(event.target.checked)} /><span className="mail-switch-track" aria-hidden="true"><span className="mail-switch-thumb" /></span><span className="mail-switch-state">{mailPreference.habilitado ? 'Activados' : 'Desactivados'}</span></label> : !mailError && <p className="small-note mail-settings-status">Consultando preferencia de correo…</p>}</div>
      {mailPreference && !mailPreference.disponible && <p className="small-note mail-settings-status">El envío por correo aún no está habilitado.</p>}
      <Message>{mailError}</Message></section>
    {!current && <p role="status"><Icon name="loading" />Cargando notificaciones…</p>}
    {current?.error && <><Message>{current.error}</Message><Button icon="refresh" onClick={() => setRevision((value) => value + 1)}>Reintentar</Button></>}
    <Message>{error}</Message>
    {current?.data && <><p className="results-count notification-count">{current.data.no_leidas} sin leer · {current.data.count} en total</p>
      {!current.data.count ? <section className="profile-card"><h2>Aún no tienes notificaciones</h2><p>Cuando se publique una beca abierta relacionada con tus datos declarados que no sea claramente incompatible con tu perfil, o cuando una de tus becas favoritas esté por cerrar, aparecerá aquí.</p></section> :
        groups.map(([id, title, items]) => items.length > 0 && <section className="notification-group" key={id} aria-labelledby={`notificaciones-${id}`}>
          <h2 id={`notificaciones-${id}`}>{title} <span className="notification-group-count">({items.length})</span></h2>
          <ul className="notification-list">{items.map(card)}</ul>
        </section>)}
      {current.data.count > current.data.page_size && <nav className="pagination" aria-label="Paginación de notificaciones"><Button icon="previous" disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button icon="next" disabled={page * current.data.page_size >= current.data.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}
    </>}
  </OffersLayout>
}
