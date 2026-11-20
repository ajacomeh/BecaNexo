import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import './OriginPanel.css'

const path = (id) => `gestion/rastreo/convocatorias/${id}/origen`
const publicUrl = (value) => {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null } catch { return null }
}
const recordKinds = { requisitos: 'Requisito', beneficios: 'Beneficio', opciones: 'Opción de estudio' }
const fieldLabels = { url_oficial: 'Enlace oficial', url_bases: 'Enlace de las bases', tipo_beca: 'Tipo de beca',
  cobertura_tipo: 'Cobertura', gastos_no_cubiertos: 'Gastos no cubiertos', obligaciones_beneficiario: 'Obligaciones de la persona becaria',
  institucion: 'Entidad oferente', fecha_publicacion: 'Fecha de publicación', areas: 'Áreas académicas', apertura: 'Apertura' }

function Source({ item }) {
  const section = item.seccion ? ` · Sección: ${item.seccion}` : ''
  const page = item.pagina ? ` · Página ${item.pagina}` : ''
  return <span className="small-note">{item.documento_id ? `Documento ${item.documento_id}` : 'Documento de la ficha'}{section}{page}</span>
}

function OriginEvidence({ evidence }) {
  const fields = evidence?.campos || []
  const records = evidence?.registros || []
  if (!fields.length && !records.length) return null
  return <details className="origin-evidence"><summary>Ver evidencia de origen</summary>
    <p className="small-note">Texto literal de la fuente y documento de donde salió cada dato cargado automáticamente. Se edita, elimina y valida desde las secciones normales.</p>
    <ul className="origin-candidate-list">
      {fields.map((item) => <li key={`campo-${item.campo}`} className="origin-candidate">
        <p className="origin-candidate-text"><strong>{fieldLabels[item.campo] || item.campo}:</strong> {item.nombre ? `${item.nombre}${item.entidad_creada ? ' (entidad creada automáticamente)' : ''} — ${item.literal}` : (item.literal || item.valor)}</p><Source item={item} /></li>)}
      {records.map((item) => <li key={`${item.modelo}-${item.id}`} className="origin-candidate">
        <p className="origin-candidate-text"><strong>{recordKinds[item.modelo] || item.modelo}:</strong> {item.texto}</p><Source item={item} /></li>)}
    </ul></details>
}

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
  async function confirmVersion(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await offersApi.write(path(offer.id), 'POST', {
        version_id: data.version_actual_id, version_convocatoria: data.version_convocatoria, motivo: motive,
      })
      setMotive(''); setNotice('Revisión de la versión registrada. Comprueba los demás campos antes de publicar.'); setRetry((v) => v + 1)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  if (!data && !error) return <section className="profile-card"><h2>Procedencia del rastreo</h2><p role="status">Consultando origen…</p></section>
  if (error && !data) return <section className="profile-card"><h2>Procedencia del rastreo</h2><Message>{error}</Message><Button type="button" onClick={() => setRetry((v) => v + 1)}>Reintentar consulta</Button></section>
  if (data?.automatico) {
    const source = publicUrl(data.enlaces_origen?.publicacion)
    const bases = (data.enlaces_origen?.bases || []).map((item) => publicUrl(item.url)).filter(Boolean)
    const missing = data.para_publicar || []
    return <section className="profile-card crawl-origin"><h2>Borrador generado por rastreo</h2>
      <p>Publicación {data.publicacion_id} · Versión {data.version_id}. Ninguna beca se publica automáticamente.</p>
      <p><Link to={`/gestion/rastreo/publicaciones/${data.publicacion_id}`}>Consultar ficha, versiones y documentos originales</Link>
        {source && <> · <a href={source} target="_blank" rel="noopener noreferrer">Abrir ficha de origen</a></>}
        {bases.map((url, index) => <span key={url}> · <a href={url} target="_blank" rel="noopener noreferrer">Bases {index + 1}</a></span>)}</p>
      {data.cambio_relevante && <p role="status">La versión {data.version_actual_id} contiene cambios posteriores al borrador. Las ediciones administrativas se conservan.</p>}
      {data.cambio_relevante && !data.revision_confirmada && <form onSubmit={confirmVersion}><label htmlFor="origin-version-motive">Motivo de revisión de la nueva versión</label><textarea id="origin-version-motive" required maxLength={1000} value={motive} onChange={(e) => setMotive(e.target.value)} /><Button type="submit" disabled={busy} busy={busy}>Confirmar versión revisada</Button></form>}
      {error && <Message>{error}</Message>}{notice && <p role="status">{notice}</p>}
      <h3>Para publicar falta</h3>{missing.length ? <ul>{missing.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No falta nada. La publicación requiere tu confirmación.</p>}
      <OriginEvidence evidence={data.evidencia} />
    </section>
  }
  if (!data?.aplicacion) return null
  const pending = data.estado?.pendientes || []
  const blockers = data.estado?.bloqueos || []
  return <section className="profile-card crawl-origin"><h2>Procedencia del rastreo</h2>
    <p>Publicación {data.publicacion_id} · Versión ID {data.version_id} · Observación {data.observacion_base_id} · Propuesta {data.aplicacion.propuesta_id}. La revisión documental corresponde a la evidencia exacta; no verifica documentos del postulante.</p>
    <Link to={`/gestion/rastreo/publicaciones/${data.publicacion_id}`}>Consultar propuesta, revisiones y documentos</Link>
    {Object.keys(data.aplicacion.opciones_ids || {}).length > 0 && <details><summary>Correspondencias de opciones creadas</summary><ul>{Object.entries(data.aplicacion.opciones_ids).map(([candidateId, optionId]) => <li key={candidateId}>Candidato {candidateId} → opción {optionId}: {offer.opciones?.find(o => o.id === optionId)?.programa || 'Programa no especificado'}</li>)}</ul></details>}
    {error && <Message>{error}</Message>}{notice && <p role="status">{notice}</p>}
    {blockers.length > 0 && <><h3>Revisiones de origen pendientes</h3><ul>{blockers.map((x) => <li key={x.id}>{x.motivo}</li>)}</ul></>}
    <h3>Pendientes materiales de publicación</h3>{pending.length ? <ul>{pending.map((x) => <li key={x.id}>{x.campo}: {x.motivo} <small>({x.id})</small></li>)}</ul> : <p>No quedan pendientes materiales de la aplicación actual.</p>}
    {data.resoluciones?.length > 0 && <details><summary>Resoluciones registradas</summary><ul>{data.resoluciones.map((r) => <li key={r.id}>{r.pendiente_id} · {r.motivo} · Evidencia {r.evidencia_id}{r.opcion_estudio_id && ` · Candidato ${r.opcion_candidata_id} → opción ${r.opcion_estudio_id}`}</li>)}</ul></details>}
    {pending.length > 0 && <form onSubmit={resolve}><h3>Registrar resolución comprobada</h3><p>Completa primero los datos canónicos en el editor. El servidor exige evidencia revisada de la versión exacta; los valores ambiguos siguen pendientes.</p>
      <div className="field"><label htmlFor="origin-pending">Pendiente</label><select id="origin-pending" required value={issue} onChange={(e) => setIssue(e.target.value)}><option value="">Selecciona un pendiente</option>{pending.map((x) => <option key={x.id} value={x.id} disabled={x.codigo === 'PRECISION_TEMPORAL' && x.campo === 'apertura_original'}>{x.campo} · {x.codigo}{x.codigo === 'PRECISION_TEMPORAL' && x.campo === 'apertura_original' ? ' · apertura por día aún no representada' : ''}</option>)}</select></div>
      <div className="field"><label htmlFor="origin-evidence">Evidencia documental revisada</label><select id="origin-evidence" required value={evidence} onChange={(e) => setEvidence(e.target.value)}><option value="">Selecciona relación exacta</option>{documents.map((d) => <option key={d.evidencia_id} value={d.evidencia_id}>{d.rol} · Relación {d.evidencia_id}</option>)}</select></div>
      <div className="field"><label htmlFor="origin-motive">Justificación y comprobación</label><textarea id="origin-motive" required maxLength={5000} value={motive} onChange={(e) => setMotive(e.target.value)} /></div>
      <Button type="submit" busy={busy} disabled={busy}>Registrar resolución</Button>
    </form>}
  </section>
}
