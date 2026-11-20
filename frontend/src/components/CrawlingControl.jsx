import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import { remaining } from './crawlTime'

const path = 'gestion/rastreo/control'
const date = value => value ? new Date(value).toLocaleString('es-EC') : 'Sin fecha programada'
const waiting = (value, now) => now > 0 && value && new Date(value).getTime() > now

function SourceBlock({ block, onUnlocked }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const key = useRef(null)
  const valid = reason.trim().length >= 10 && reason.trim().length <= 500
  async function unlock(event) {
    event.preventDefault()
    if (busy || !valid) return
    setBusy(true); setError('')
    key.current ||= crypto.randomUUID()
    try {
      await offersApi.write(`gestion/rastreo/fuentes/${block.fuente_id}/desbloquear`, 'POST', { motivo: reason.trim(), clave_accion: key.current })
      key.current = null; setOpen(false); setReason('')
      await onUnlocked()
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  return <div className="crawl-block">
    <p><strong>{block.fuente_nombre}</strong> está bloqueada desde {date(block.bloqueado_en)} por una respuesta HTTP {block.http_status}.
      {block.reintento_desde && <> La fuente pidió esperar hasta {date(block.reintento_desde)}.</>}</p>
    {!open && <Button type="button" icon="refresh" onClick={() => setOpen(true)}>Levantar bloqueo</Button>}
    {open && <form onSubmit={unlock}>
      <label htmlFor={`unlock-${block.fuente_id}`}>Motivo del desbloqueo (10 a 500 caracteres)</label>
      <textarea id={`unlock-${block.fuente_id}`} required minLength={10} maxLength={500} value={reason} disabled={busy}
        onChange={(event) => { setReason(event.target.value); key.current = null }} />
      <p className="small-note">El desbloqueo queda registrado a tu nombre. La próxima captura seguirá respetando la espera de la fuente y su frecuencia.</p>
      <Message>{error}</Message>
      <div className="crawl-confirm-actions">
        <Button type="button" disabled={busy} onClick={() => { setOpen(false); setError('') }}>Cancelar</Button>
        <Button type="submit" busy={busy} disabled={!valid}>Confirmar desbloqueo</Button>
      </div>
    </form>}
  </div>
}

function unavailableReason(state, now) {
  if (state.requiere_revision) return 'Pendiente de recuperación: revisa el proceso y su marcador.'
  if (state.ejecucion_activa) return 'Hay un rastreo en curso.'
  if (state.inicio_pendiente) return 'Hay una solicitud de inicio pendiente.'
  if (state.fuentes_habilitadas === 0 || state.fuentes_activas === 0) return 'No hay fuentes activas y autorizadas para iniciar.'
  if (state.bloqueo_fuente) return 'La fuente requiere revisión tras una respuesta HTTP 429/503.'
  if (state.registro_invalido) return 'El registro de solicitudes requiere revisión.'
  if (!now && state.proxima_manual) return 'Comprobando tiempo restante.'
  if (waiting(state.proxima_manual, now)) return `Disponible en ${remaining(state.proxima_manual, now)} por frecuencia.`
  if (!state.rastreo_extraordinario_habilitado) return 'El inicio ordinario respeta la frecuencia de cada fuente; la excepción de cinco minutos no está autorizada.'
  return 'Ninguna fuente cumple ahora sus condiciones de inicio.'
}

export default function CrawlingControl() {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const [now, setNow] = useState(0)
  const refresh = useCallback(async () => {
    try { setState(await offersApi.get(path)); setError('') }
    catch (failure) { setError(failure.message) }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(refresh, 0)
    return () => window.clearTimeout(timer)
  }, [refresh])
  useEffect(() => {
    if (state?.requiere_revision || (!state?.inicio_pendiente && !state?.ejecucion_activa)) return undefined
    const timer = window.setInterval(refresh, 3000)
    return () => window.clearInterval(timer)
  }, [state?.inicio_pendiente, state?.ejecucion_activa, state?.requiere_revision, refresh])
  useEffect(() => {
    const first = window.setTimeout(() => setNow(Date.now()), 0)
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { window.clearTimeout(first); window.clearInterval(timer) }
  }, [])

  async function start() {
    if (busy || !state?.puede_iniciar || !confirming || reason.trim().length < 10 || reason.trim().length > 240) return
    setBusy(true); setError('')
    try {
      await offersApi.write(path, 'POST', { motivo: reason.trim() })
      setState(previous => ({ ...previous, puede_iniciar: false, inicio_pendiente: true }))
      setConfirming(false); setReason('')
      await refresh()
    } catch (failure) {
      await refresh()
      setError(failure.message)
    } finally { setBusy(false) }
  }

  function dialogKeys(event) {
    if (event.key === 'Escape') { setConfirming(false); return }
    if (event.key !== 'Tab') return
    const controls = [...event.currentTarget.querySelectorAll('input, button:not(:disabled)')]
    if (event.shiftKey && document.activeElement === controls[0]) {
      event.preventDefault(); controls.at(-1)?.focus()
    } else if (!event.shiftKey && document.activeElement === controls.at(-1)) {
      event.preventDefault(); controls[0]?.focus()
    }
  }

  return <section className="profile-card crawl-control" aria-labelledby="crawl-control-title">
    <div className="crawl-control-heading"><div><h2 id="crawl-control-title">Rastreo</h2>
      <p>Descubrimiento de becas en fuentes autorizadas. Cada publicación requiere revisión antes de llegar al catálogo.</p></div>
      <Button type="button" icon="crawling" busy={busy} disabled={!state?.puede_iniciar} aria-describedby="crawl-availability" onClick={() => setConfirming(true)}>Iniciar rastreo</Button>
    </div>
    {!state && !error && <p role="status">Consultando estado del rastreo…</p>}
    <Message>{error}</Message>
    {state && <div className="crawl-control-status">
      <dl className="crawl-control-metrics"><div><dt>Fuentes activas</dt><dd>{state.fuentes_activas == null ? '—' : `${state.fuentes_activas} ${state.fuentes_activas === 1 ? 'fuente activa' : 'fuentes activas'}`}</dd></div><div><dt>Publicaciones detectadas</dt><dd>{state.publicaciones_total ?? '—'}</dd></div><div><dt>Borradores automáticos</dt><dd>{state.borradores_total ?? '—'}</dd></div></dl>
      <p>Última ejecución: {state.ultima_ejecucion ? <><Link to={`/gestion/rastreo/ejecuciones/${state.ultima_ejecucion.id}`}>#{state.ultima_ejecucion.id}</Link> · {state.ultima_ejecucion.fuente && `${state.ultima_ejecucion.fuente} · `}{state.ultima_ejecucion.estado} · {date(state.ultima_ejecucion.inicio)}</> : 'Sin ejecuciones'}.</p>
      <p className="crawl-control-scheduled">Última corrida programada: {state.ultima_programada
        ? <><Link to={`/gestion/rastreo/ejecuciones/${state.ultima_programada.ejecucion_id}`}>#{state.ultima_programada.ejecucion_id}</Link> · {state.ultima_programada.estado} · {date(state.ultima_programada.inicio)} · {state.ultima_programada.peticiones} peticiones · {state.ultima_programada.publicaciones_observadas} fichas observadas · {state.ultima_programada.candidatos_nuevos} candidatos nuevos · {state.ultima_programada.borradores_creados} borradores creados · {state.ultima_programada.incidencias_total} incidencias{state.ultima_programada.motivo ? ` · Motivo: ${state.ultima_programada.motivo}` : ''}</>
        : 'aún no hay corridas programadas'}.</p>
      <p>Próxima disponibilidad: {state.puede_iniciar ? `Disponible para ${state.fuente_nombre || 'una fuente autorizada'}` : state.proxima_manual ? `${date(state.proxima_manual)}${waiting(state.proxima_manual, now) ? ` · ${remaining(state.proxima_manual, now)}` : ''}` : 'Sin fecha disponible'}.</p>
      <p id="crawl-availability" className="crawl-control-availability">Inicio desde el panel: {state.puede_iniciar ? 'Disponible' : unavailableReason(state, now)}</p>
      {(state.bloqueos || []).map(block => <SourceBlock key={block.fuente_id} block={block} onUnlocked={refresh} />)}
      {state.ejecucion_activa && <p>Rastreo en curso · ejecución {state.ejecucion_activa}.</p>}
      {state.inicio_pendiente && !state.ejecucion_activa && <p>Inicio solicitado; esperando confirmación del proceso local.</p>}
      {state.requiere_revision && <p>El inicio lleva más de dos minutos sin cierre. Revisa el proceso y la ejecución antes de solicitar otro.</p>}
      {state.ultimo_inicio_web && <p>Último inicio desde el panel: {state.ultimo_inicio_web.estado === 'omitida_frecuencia' ? 'omitido por frecuencia' : state.ultimo_inicio_web.estado === 'omitida_concurrencia' ? 'omitido por otra ejecución' : state.ultimo_inicio_web.estado === 'fallo_infraestructura' ? 'fallo del proceso local' : state.ultimo_inicio_web.estado}.</p>}
      <details className="crawl-control-technical"><summary>Configuración y detalles técnicos</summary>
        <h3>Fuentes registradas</h3>
        {(state.fuentes_registradas || []).length ? <ul>{state.fuentes_registradas.map(source => <li key={source.id}>{source.nombre} · {source.activa ? source.utilizable ? 'Activa y autorizada' : 'Activa; configuración por revisar' : 'Inactiva'} · Política: {source.politica_version} · Frecuencia: {source.frecuencia_min} minutos</li>)}</ul> : <p>No hay fuentes registradas.</p>}
        <h3>Conectores disponibles sin fuente registrada</h3>
        {(state.conectores_sin_registro || []).length ? <ul>{state.conectores_sin_registro.map(item => <li key={item.adaptador}>{item.nombre} · No registrado ni activo</li>)}</ul> : <p>Todos los conectores específicos tienen una fuente registrada.</p>}
        <p>El conector genérico requiere registrar y verificar cada portal antes de activarlo.</p>
        <p>Rastreo manual extraordinario de 5 minutos: {state.rastreo_extraordinario_habilitado ? 'habilitado para SIAU' : 'pendiente de autorización'}.</p>
        <p>La tarea automática respeta la frecuencia de cada fuente. Las publicaciones no se aprueban automáticamente.</p>
      </details>
    </div>}
    {confirming && <div className="crawl-confirm" role="dialog" aria-modal="true" aria-labelledby="crawl-confirm-title" onKeyDown={dialogKeys}>
      <form onSubmit={event => { event.preventDefault(); start() }}>
        <h3 id="crawl-confirm-title">Confirmar inicio de rastreo</h3>
        <p>La solicitud inicia un proceso independiente. La captura no publica convocatorias.</p>
        <label htmlFor="crawl-reason">Motivo administrativo (10 a 240 caracteres)</label>
        <input id="crawl-reason" type="text" autoFocus required minLength={10} maxLength={240} value={reason} onChange={event => setReason(event.target.value)} />
        <div className="crawl-confirm-actions">
          <Button type="button" disabled={busy} onClick={() => setConfirming(false)}>Cancelar</Button>
          <Button type="submit" busy={busy} disabled={!state?.puede_iniciar || reason.trim().length < 10}>Confirmar inicio</Button>
        </div>
      </form>
    </div>}
  </section>
}
