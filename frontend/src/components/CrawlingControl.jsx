import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import { remaining } from './crawlTime'

const path = 'gestion/rastreo/control'
const date = value => value ? new Date(value).toLocaleString('es-EC') : 'Sin fecha programada'
const waiting = (value, now) => now > 0 && value && new Date(value).getTime() > now

function unavailableReason(state, now) {
  if (state.requiere_revision) return 'Pendiente de recuperación: revisa el proceso y su marcador.'
  if (state.ejecucion_activa) return 'Hay un rastreo en curso.'
  if (state.inicio_pendiente) return 'Hay una solicitud de inicio pendiente.'
  if (state.bloqueo_fuente) return 'La fuente requiere revisión tras una respuesta HTTP 429/503.'
  if (state.registro_invalido) return 'El registro de solicitudes requiere revisión.'
  if (!now && state.proxima_manual) return 'Comprobando tiempo restante.'
  if (waiting(state.proxima_manual, now)) return `Disponible en ${remaining(state.proxima_manual, now)} por frecuencia.`
  if (!state.rastreo_extraordinario_habilitado) return 'La excepción de cinco minutos no está autorizada; el inicio ordinario respeta las 24 horas.'
  return 'La fuente o su configuración no permite iniciar ahora.'
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
    <div className="crawl-control-heading"><div><h2 id="crawl-control-title">Rastreo SIAU</h2>
      <p>Consulta publicaciones oficiales; los resultados requieren revisión administrativa antes de aparecer en el catálogo.</p></div>
      <Button type="button" icon="crawling" busy={busy} disabled={!state?.puede_iniciar} aria-describedby="crawl-availability" onClick={() => setConfirming(true)}>Iniciar rastreo</Button>
    </div>
    {!state && !error && <p role="status">Consultando estado del rastreo…</p>}
    <Message>{error}</Message>
    {state && <div className="crawl-control-status">
      <p className="crawl-control-source">Fuente: SIAU · Política: {state.politica_version}.</p>
      <div className="crawl-control-modes">
        <section className="crawl-control-mode" aria-labelledby="crawl-automatic-title">
          <h3 id="crawl-automatic-title">Rastreo automático</h3>
          <p>Frecuencia: cada {state.frecuencia_min === 1440 ? '24 horas (1440 minutos)' : `${state.frecuencia_min} minutos`}.</p>
          <p>Próxima ventana permitida: {date(state.proxima_ejecucion)}.</p>
          <p>Estado: {state.ejecucion_activa ? 'ocupado por una captura en curso' : !now && state.proxima_ejecucion ? 'calculando espera' : waiting(state.proxima_ejecucion, now) ? `en espera · ${remaining(state.proxima_ejecucion, now)}` : state.proxima_ejecucion ? 'ventana cumplida; pendiente del Programador' : 'sin ejecución previa'}.</p>
        </section>
        <section className="crawl-control-mode" aria-labelledby="crawl-manual-title">
          <h3 id="crawl-manual-title">Rastreo manual</h3>
          <p>Intervalo extraordinario propuesto: 5 minutos.</p>
          <p>Estado: {state.rastreo_extraordinario_habilitado ? 'habilitado' : 'pendiente de autorización'}.</p>
          <p>{state.rastreo_extraordinario_habilitado ? 'Próxima ejecución manual permitida' : 'Próximo inicio manual ordinario'}: {date(state.proxima_manual)}.</p>
        </section>
      </div>
      <p id="crawl-availability" className="crawl-control-availability">Inicio desde el panel: {state.puede_iniciar ? 'Disponible' : unavailableReason(state, now)}</p>
      {state.ejecucion_activa && <p>Rastreo en curso · ejecución {state.ejecucion_activa}.</p>}
      {state.inicio_pendiente && !state.ejecucion_activa && <p>Inicio solicitado; esperando confirmación del proceso local.</p>}
      {state.requiere_revision && <p>El inicio lleva más de dos minutos sin cierre. Revisa el proceso y la ejecución antes de solicitar otro.</p>}
      {state.ultimo_inicio_web && <p>Último inicio desde el panel: {state.ultimo_inicio_web.estado === 'omitida_frecuencia' ? 'omitido por frecuencia' : state.ultimo_inicio_web.estado === 'omitida_concurrencia' ? 'omitido por otra ejecución' : state.ultimo_inicio_web.estado === 'fallo_infraestructura' ? 'fallo del proceso local' : state.ultimo_inicio_web.estado}.</p>}
      {state.ultima_ejecucion && <p>Última ejecución: <Link to={`/gestion/rastreo/ejecuciones/${state.ultima_ejecucion.id}`}>#{state.ultima_ejecucion.id}</Link> · {state.ultima_ejecucion.estado}.</p>}
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
