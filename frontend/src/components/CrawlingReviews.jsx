import { useEffect, useRef, useState } from 'react'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

const dimensions = { extraccion: 'Extracción', documental: 'Documentación', oferente: 'Oferente' }
const decisions = { pendiente: 'Pendiente', aprobada: 'Aprobada', rechazada: 'Rechazada' }

export default function CrawlingReviews({ publication, version }) {
  const path = `gestion/rastreo/publicaciones/${publication}/versiones/${version}/revisiones`
  const [data, setData] = useState(null)
  const [documents, setDocuments] = useState([])
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({ dimension: 'extraccion', decision: 'pendiente', motivo: '', evidencia_id: '', tipo_oferente: 'no_determinado', referencia: '' })
  const action = useRef(null)
  const sending = useRef(false)
  useEffect(() => {
    let live = true
    async function load() {
      try {
        const result = await offersApi.get(path, { page })
        const docs = []
        let next = 1, response
        do {
          response = await offersApi.get(`gestion/rastreo/publicaciones/${publication}/versiones/${version}/documentos`, { page: next, page_size: 50 })
          docs.push(...response.results)
          next += 1
        } while ((next - 1) * response.page_size < response.count)
        if (live) { setData(result); setDocuments(docs); setLoaded(true) }
      } catch (failure) { if (live) setError(failure.message) }
    }
    load()
    return () => { live = false }
  }, [path, publication, version, page, retry])
  function refresh() { setLoaded(false); setError(''); setRetry(value => value + 1) }
  const currents = data?.vigentes || []
  function evidenceLabel(id) {
    const document = documents.find(item => item.evidencia_id === id)
    return document ? `Documento ${document.id} · ${document.rol} · relación ${id}` : `Evidencia vinculada ${id}`
  }
  const current = currents.find(r => r.dimension === form.dimension && (form.dimension !== 'documental' || r.evidencia_id === Number(form.evidencia_id)))
  function change(event) { setForm(value => ({ ...value, [event.target.name]: event.target.value })); setSuccess('') }
  async function save(event) {
    event.preventDefault()
    if (sending.current || !loaded) return
    const payload = { dimension: form.dimension, decision: form.decision, motivo: form.motivo, evidencia_id: form.dimension === 'extraccion' ? null : Number(form.evidencia_id), sustituye_id: current?.id || null,
      ...(form.dimension === 'oferente' ? { tipo_oferente: form.tipo_oferente, referencia: form.referencia } : {}) }
    const signature = JSON.stringify(payload)
    if (action.current?.signature !== signature) action.current = { signature, key: crypto.randomUUID() }
    sending.current = true; setBusy(true); setError(''); setSuccess('')
    try {
      await offersApi.write(path, 'POST', { ...payload, clave_accion: action.current.key })
      setSuccess('Revisión guardada. No publica ni aprueba otras versiones.'); setEditing(false)
      setForm(value => ({ ...value, motivo: '', referencia: '' })); action.current = null; refresh()
    } catch (failure) {
      const fields = Object.values(failure.fields || {}).flat().filter(value => typeof value === 'string')
      setError(fields.length ? fields.join(' ') : failure.message)
    } finally { sending.current = false; setBusy(false) }
  }
  return <section className="profile-card crawl-reviews" aria-labelledby="reviews-title">
    <h2 id="reviews-title">Revisiones administrativas</h2>
    <p>Decisiones independientes sobre esta versión. No modifican la vigencia, el catálogo ni las incidencias.</p>
    <Message kind="success">{success}</Message><Message>{error}</Message>
    {error && <Button icon="refresh" disabled={busy} onClick={refresh}>Actualizar historial antes de reintentar</Button>}
    {!loaded && !error && <p role="status">Cargando revisiones…</p>}
    {data && <>
      <p><strong>Versión {data.numero}</strong> · {data.ultima_observada ? 'Última observación exitosa' : 'Evidencia histórica: esta revisión no aprueba la última versión observada'}</p>
      <h3>Decisiones vigentes de esta versión</h3>
      {!currents.length && <p>Sin revisiones registradas. Información pendiente de revisión.</p>}
      {['extraccion', 'oferente'].filter(dimension => !currents.some(r => r.dimension === dimension)).map(dimension => <p key={dimension}>{dimensions[dimension]}: pendiente de revisión, sin decisión registrada.</p>)}
      {documents.filter(d => !currents.some(r => r.dimension === 'documental' && r.evidencia_id === d.evidencia_id)).map(d => <p key={d.evidencia_id}>Documento {d.id} ({d.rol}): pendiente de revisión, sin decisión registrada.</p>)}
      <ul>{currents.map(r => <li key={r.id}>{dimensions[r.dimension]}{r.evidencia_id ? ` · ${evidenceLabel(r.evidencia_id)}` : ''}: {decisions[r.decision]} · Revisión {r.id}</li>)}</ul>
      {!editing ? <Button icon="edit" disabled={!loaded} onClick={() => setEditing(true)}>Registrar revisión</Button> : <form onSubmit={save} className="crawl-review-form">
        <h3>Registrar decisión sobre la versión {data.numero}</h3>
        <p>Guardar modifica el historial. Examine la evidencia antes de confirmar; no use documentos reales para ensayos.</p>
        <label htmlFor="review-dimension"><span>Dimensión</span><select id="review-dimension" aria-label="Dimensión" name="dimension" value={form.dimension} onChange={change} disabled={busy}>{Object.entries(dimensions).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        {form.dimension !== 'extraccion' && <label htmlFor="review-evidencia_id"><span>Evidencia exacta</span><select id="review-evidencia_id" aria-label="Evidencia exacta" name="evidencia_id" value={form.evidencia_id} onChange={change} required disabled={busy}><option value="">Seleccione un documento</option>{documents.map(d => <option key={d.evidencia_id} value={d.evidencia_id}>Documento {d.id} · {d.rol} · {d.mime} · {d.sha256}</option>)}</select></label>}
        {form.dimension === 'oferente' && <><label htmlFor="review-tipo_oferente"><span>Tipo de oferente</span><select id="review-tipo_oferente" aria-label="Tipo de oferente" name="tipo_oferente" value={form.tipo_oferente} onChange={change} disabled={busy}><option value="no_determinado">No determinado</option><option value="entidad_ecuatoriana">Entidad ecuatoriana</option><option value="convenio">Convenio (aprobación no habilitada)</option></select></label><label>Referencia en la evidencia<textarea name="referencia" value={form.referencia} onChange={change} required maxLength={2000} disabled={busy} /></label><p>La mera difusión no acredita participación formal ecuatoriana. No se habilita la aprobación de convenios.</p></>}
        <label htmlFor="review-decision"><span>Decisión</span><select id="review-decision" aria-label="Decisión" name="decision" value={form.decision} onChange={change} disabled={busy}>{Object.entries(decisions).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>
        <label>Justificación<textarea name="motivo" value={form.motivo} onChange={change} required maxLength={5000} disabled={busy} /></label>
        <p>Destino: versión {data.numero}{form.dimension !== 'extraccion' && form.evidencia_id ? `, documento ${documents.find(d => d.evidencia_id === Number(form.evidencia_id))?.id}, relación de evidencia ${form.evidencia_id}` : ', extracción completa'} · {current ? `Sustituye revisión ${current.id}; conserva la anterior.` : 'Primera revisión de esta dimensión/evidencia.'}</p>
        <div className="heading-actions"><Button icon="save" type="submit" busy={busy} disabled={!loaded}>Guardar revisión</Button><Button icon="cancel" type="button" disabled={busy} onClick={() => { setEditing(false); setError('') }}>Cancelar</Button></div>
      </form>}
      <details><summary>Historial de revisiones</summary><ul className="record-list crawl-list">{data.results.map(r => <li key={r.id}><article><h3>Revisión {r.id} · {dimensions[r.dimension]} · {decisions[r.decision]}</h3><p>{r.administrador.nombre} · {new Date(r.creada_en).toLocaleString('es-EC')}</p><p>{r.evidencia_id ? evidenceLabel(r.evidencia_id) : 'Versión completa'} · {r.sustituye_id ? `Sustituye revisión ${r.sustituye_id}` : 'Primera decisión'}</p><p className="crawl-text">{r.motivo}</p>{r.detalle?.referencia && <p className="crawl-text">Referencia manual: {r.detalle.referencia}</p>}</article></li>)}</ul>
        {data.count > data.page_size && <nav className="pagination" aria-label="Paginación de revisiones"><Button icon="previous" disabled={page === 1 || !loaded || busy} onClick={() => { setLoaded(false); setPage(page - 1) }}>Anterior</Button><span>Página {page}</span><Button icon="next" disabled={page * data.page_size >= data.count || !loaded || busy} onClick={() => { setLoaded(false); setPage(page + 1) }}>Siguiente</Button></nav>}
      </details>
    </>}
  </section>
}
