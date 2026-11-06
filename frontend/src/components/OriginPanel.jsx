import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

const path = (id) => `gestion/rastreo/convocatorias/${id}/origen`

export default function OriginPanel({ offer }) {
  const [data, setData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(0)
  const [issue, setIssue] = useState('')
  const [evidence, setEvidence] = useState('')
  const [motive, setMotive] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let live = true
    offersApi.get(path(offer.id)).then(async (origin) => {
      if (!live) return
      setData(origin); setError('')
      if (origin.aplicacion) {
        const rows = []; let page = 1; let response
        do {
          response = await offersApi.get(`gestion/rastreo/publicaciones/${origin.publicacion_id}/versiones/${origin.version_id}/documentos`, { page, page_size: 50 })
          rows.push(...response.results); page += 1
        } while (rows.length < response.count)
        if (live) setDocuments(rows)
      }
    }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [offer.id, offer.version, retry])

  async function resolve(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await offersApi.write(path(offer.id), 'POST', {
        clave_accion: crypto.randomUUID(), pendiente_id: issue, evidencia_id: Number(evidence), motivo: motive,
        version_convocatoria: data.version_convocatoria, hash_convocatoria: data.hash_convocatoria,
      })
      setNotice('Resolución registrada. Revisa nuevamente el estado antes de publicar.')
      setIssue(''); setEvidence(''); setMotive(''); setRetry((v) => v + 1)
    } catch (e) { setError(`${e.message} Conservamos la justificación y la evidencia seleccionada para corregir o reintentar.`) }
    finally { setBusy(false) }
  }
  if (!data && !error) return <section className="profile-card"><h2>Procedencia del rastreo</h2><p role="status">Consultando origen…</p></section>
  if (error && !data) return <section className="profile-card"><h2>Procedencia del rastreo</h2><Message>{error}</Message><Button type="button" onClick={() => setRetry((v) => v + 1)}>Reintentar consulta</Button></section>
  if (!data?.aplicacion) return null
  const pending = data.estado?.pendientes || []
  const blockers = data.estado?.bloqueos || []
  return <section className="profile-card crawl-origin"><h2>Procedencia del rastreo</h2>
    <p>Publicación {data.publicacion_id} · Versión ID {data.version_id} · Observación {data.observacion_base_id} · Propuesta {data.aplicacion.propuesta_id}. La revisión documental corresponde a la evidencia exacta; no verifica documentos del postulante.</p>
    <Link to={`/gestion/rastreo/publicaciones/${data.publicacion_id}`}>Consultar propuesta, revisiones y documentos</Link>
    {error && <Message>{error}</Message>}{notice && <p role="status">{notice}</p>}
    {blockers.length > 0 && <><h3>Revisiones de origen pendientes</h3><ul>{blockers.map((x) => <li key={x.id}>{x.motivo}</li>)}</ul></>}
    <h3>Pendientes materiales de publicación</h3>{pending.length ? <ul>{pending.map((x) => <li key={x.id}>{x.campo}: {x.motivo} <small>({x.id})</small></li>)}</ul> : <p>No quedan pendientes materiales de la aplicación actual.</p>}
    {data.resoluciones?.length > 0 && <details><summary>Resoluciones registradas</summary><ul>{data.resoluciones.map((r) => <li key={r.id}>{r.pendiente_id} · {r.motivo} · Evidencia {r.evidencia_id}</li>)}</ul></details>}
    {pending.length > 0 && <form onSubmit={resolve}><h3>Registrar resolución comprobada</h3><p>Completa primero los datos en el editor. Las fechas sin hora y los topes sin representación permanecen bloqueados.</p>
      <div className="field"><label htmlFor="origin-pending">Pendiente</label><select id="origin-pending" required value={issue} onChange={(e) => setIssue(e.target.value)}><option value="">Selecciona un pendiente</option>{pending.map((x) => <option key={x.id} value={x.id} disabled={['PRECISION_TEMPORAL', 'TOPE_FUENTE', 'TOPE_NO_REPRESENTADO'].includes(x.codigo)}>{x.campo} · {x.codigo}{['PRECISION_TEMPORAL', 'TOPE_FUENTE', 'TOPE_NO_REPRESENTADO'].includes(x.codigo) ? ' · requiere ampliar el modelo' : ''}</option>)}</select></div>
      <div className="field"><label htmlFor="origin-evidence">Evidencia documental revisada</label><select id="origin-evidence" required value={evidence} onChange={(e) => setEvidence(e.target.value)}><option value="">Selecciona relación exacta</option>{documents.map((d) => <option key={d.evidencia_id} value={d.evidencia_id}>{d.rol} · Relación {d.evidencia_id}</option>)}</select></div>
      <div className="field"><label htmlFor="origin-motive">Justificación y comprobación</label><textarea id="origin-motive" required maxLength={5000} value={motive} onChange={(e) => setMotive(e.target.value)} /></div>
      <Button type="submit" busy={busy} disabled={busy}>Registrar resolución</Button>
    </form>}
  </section>
}
