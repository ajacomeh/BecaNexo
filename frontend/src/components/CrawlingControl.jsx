import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import { remaining } from './crawlTime'
import { estadoEjecucion } from '../pages/estadoEjecucion'

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

// [motivo, visible]: lo que depende de la frecuencia (o ya se informa en otra línea) queda solo en el tooltip accesible;
// las causas que exigen actuar (sin fuentes, bloqueo, registro) se muestran a la vista.
function unavailableReason(state, now) {
  if (state.requiere_revision) return ['Pendiente de recuperación: revisa el proceso y su marcador.', false]
  if (state.ejecucion_activa) return ['Hay un rastreo en curso.', false]
  if (state.inicio_pendiente) return ['Hay una solicitud de inicio pendiente.', false]
  if (state.fuentes_habilitadas === 0 || state.fuentes_activas === 0) return ['No hay fuentes activas y autorizadas para iniciar.', true]
  if (state.bloqueo_fuente) return ['La fuente requiere revisión tras una respuesta HTTP 429/503.', true]
  if (state.registro_invalido) return ['El registro de solicitudes requiere revisión.', true]
  if (!now && state.proxima_manual) return ['Comprobando tiempo restante.', false]
  if (waiting(state.proxima_manual, now)) return [`Disponible en ${remaining(state.proxima_manual, now)} por frecuencia.`, false]
  if (!state.rastreo_extraordinario_habilitado) return ['El inicio ordinario respeta la frecuencia de cada fuente; la excepción de cinco minutos no está autorizada.', false]
  return ['Ninguna fuente cumple ahora sus condiciones de inicio.', false]
}

// Misma etiqueta que la lista y el detalle de Ejecuciones: «Completada con avisos» depende de las incidencias
// de aviso de esa ejecución, que se leen de su detalle (si la consulta falla, se muestra el estado sin avisos).
function RunState({ run }) {
  const [warnings, setWarnings] = useState({ id: null, count: 0 })
  useEffect(() => {
    if (run.estado !== 'finalizada') return undefined
    let live = true
    offersApi.get(`gestion/rastreo/ejecuciones/${run.id}`)
      .then((data) => { if (live) setWarnings({ id: run.id, count: Number(data?.incidencias_aviso) || 0 }) })
      .catch(() => {})
    return () => { live = false }
  }, [run.id, run.estado])
  return estadoEjecucion(run.estado, warnings.id === run.id ? warnings.count : 0)
}

const fallosDeInicio = { omitida_concurrencia: 'otra ejecución estaba en curso', fallo_infraestructura: 'fallo del proceso local' }

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

  const blocked = !state?.puede_iniciar
  const [blockReason, visibleReason] = !blocked ? [null, false] : state ? unavailableReason(state, now)
    : [error ? 'No se pudo consultar el estado del rastreo.' : 'Consultando estado del rastreo…', false]
  // Última corrida: la más reciente; las incidencias se conocen cuando coincide con la última programada.
  const run = state?.ultima_ejecucion || (state?.ultima_programada && { id: state.ultima_programada.ejecucion_id, estado: state.ultima_programada.estado, inicio: state.ultima_programada.inicio })
  const incidents = run && state?.ultima_programada?.ejecucion_id === run.id ? state.ultima_programada.incidencias_total : 0
  const failedStart = fallosDeInicio[state?.ultimo_inicio_web?.estado]

  return <section className="profile-card crawl-control" aria-labelledby="crawl-control-title">
    <div className="crawl-control-heading"><h2 id="crawl-control-title">Rastreo</h2>
      {/* aria-disabled en vez de disabled: el botón sigue siendo enfocable con el teclado y anuncia su motivo. */}
      <span className="crawl-start">
        <Button type="button" icon="crawling" busy={busy} aria-disabled={blocked ? 'true' : undefined}
          aria-describedby={blockReason ? 'crawl-availability' : undefined} onClick={() => { if (!blocked) setConfirming(true) }}>Iniciar rastreo</Button>
        {blockReason && !visibleReason && <span id="crawl-availability" role="tooltip" className="crawl-tooltip">{blockReason}</span>}
      </span>
    </div>
    {!state && !error && <p role="status">Consultando estado del rastreo…</p>}
    <Message>{error}</Message>
    {state && <div className="crawl-control-status">
      <dl className="crawl-control-metrics"><div><dt>Fuentes activas</dt><dd>{state.fuentes_activas == null ? '—' : `${state.fuentes_activas} ${state.fuentes_activas === 1 ? 'fuente activa' : 'fuentes activas'}`}</dd></div><div><dt>Publicaciones detectadas</dt><dd>{state.publicaciones_total ?? '—'}</dd></div><div><dt>Borradores automáticos</dt><dd>{state.borradores_total ?? '—'}</dd></div></dl>
      <p className="crawl-control-line">Última corrida: {run ? <><Link to={`/gestion/rastreo/ejecuciones/${run.id}`}>#{run.id}</Link> · <RunState run={run} />{run.inicio && ` · ${date(run.inicio)}`}{incidents > 0 && ` · ${incidents} ${incidents === 1 ? 'incidencia' : 'incidencias'}`}</> : 'sin ejecuciones'}</p>
      <p className="crawl-control-line">Próxima disponibilidad: {state.puede_iniciar ? `disponible ahora para ${state.fuente_nombre || 'una fuente autorizada'}` : state.proxima_manual ? `${date(state.proxima_manual)}${waiting(state.proxima_manual, now) ? ` · ${remaining(state.proxima_manual, now)}` : ''}` : 'sin fecha disponible'}</p>
      {blockReason && visibleReason && <p id="crawl-availability" className="crawl-control-availability">No se puede iniciar: {blockReason}</p>}
      {failedStart && <p className="crawl-control-availability">El último inicio desde el panel no se completó: {failedStart}.</p>}
      {(state.bloqueos || []).map(block => <SourceBlock key={block.fuente_id} block={block} onUnlocked={refresh} />)}
      {state.ejecucion_activa && <p>Rastreo en curso · ejecución {state.ejecucion_activa}.</p>}
      {state.inicio_pendiente && !state.ejecucion_activa && <p>Inicio solicitado; esperando confirmación del proceso local.</p>}
      {state.requiere_revision && <p>El inicio lleva más de dos minutos sin cierre. Revisa el proceso y la ejecución antes de solicitar otro.</p>}
      <details className="crawl-control-technical"><summary>Configuración y detalles técnicos</summary>
        <h3>Fuentes registradas</h3>
        {(state.fuentes_registradas || []).length ? <ul>{state.fuentes_registradas.map(source => <li key={source.id}>{source.nombre} · {source.activa ? source.utilizable ? 'Activa y autorizada' : 'Activa; configuración por revisar' : 'Inactiva'} · Política: {source.politica_version} · Frecuencia: {source.frecuencia_min} minutos</li>)}</ul> : <p>No hay fuentes registradas.</p>}
        <p>Las publicaciones no se aprueban automáticamente.</p>
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
