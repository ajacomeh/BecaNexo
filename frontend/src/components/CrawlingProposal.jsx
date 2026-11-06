import { useEffect, useRef, useState } from 'react'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import Field from './Field'
import CrawlingDraft from './CrawlingDraft'

const prefix = 'gestion/rastreo'
const groups = { opciones: 'Opciones de estudio', beneficios: 'Beneficios', requisitos: 'Requisitos' }
const fields = { opciones: { texto: 'Programa o mención original', nivel: 'Nivel candidato (sin equivalencias inferidas)', modalidad: 'Modalidad mencionada', destinos: 'Destinos mencionados' }, beneficios: { texto: 'Descripción', concepto: 'Concepto financiado', porcentaje: 'Porcentaje literal', monto: 'Importe fijo literal', moneda: 'Moneda explícita', tope: 'Tope literal', condiciones: 'Condiciones' }, requisitos: { texto: 'Texto original', tipo: 'Tipo candidato', condiciones: 'Condiciones según las bases' } }

function validationMessages(value) {
  if (typeof value === 'string') return [value]
  return value && typeof value === 'object' ? Object.values(value).flatMap(validationMessages) : []
}

function Scope({ item, options, countries, onChange }) {
  const available = options.find((option) => option.id === item.opcion)?.paises || []
  return <div className="form-grid">
    <div className="field"><label htmlFor={`${item.id}-scope`}>Ámbito candidato</label><select id={`${item.id}-scope`} value={item.ambito || 'pendiente'} onChange={(e) => onChange({ ...item, ambito: e.target.value })}><option value="pendiente">Pendiente de interpretar</option><option value="comun">Toda la convocatoria</option><option value="opcion">Una opción</option><option value="destino">Un destino de una opción</option></select></div>
    {(['opcion', 'destino'].includes(item.ambito) || item.opcion) && <div className="field"><label htmlFor={`${item.id}-option`}>Opción candidata</label><select id={`${item.id}-option`} value={item.opcion || ''} onChange={(e) => onChange({ ...item, opcion: e.target.value })}><option value="">Pendiente</option>{options.map((option, i) => <option key={option.id} value={option.id}>{option.texto || `Opción ${i + 1}`}</option>)}</select></div>}
    {(item.ambito === 'destino' || item.destino) && <div className="field"><label htmlFor={`${item.id}-destination`}>Destino de la opción</label><select id={`${item.id}-destination`} value={item.destino || ''} onChange={(e) => onChange({ ...item, destino: e.target.value })}><option value="">Pendiente</option>{item.destino && !available.includes(item.destino) && <option value={item.destino}>{item.destino} — pendiente de corregir</option>}{available.map((code) => <option key={code} value={code}>{countries.find((country) => country.codigo === code)?.nombre || code}</option>)}</select></div>}
    <p>Los valores anteriores se conservan al cambiar ámbito. Retira explícitamente una opción o destino si ya no corresponde.</p>
  </div>
}

function Results({ data }) {
  return <>{[['bloqueos', 'Bloqueos para crear el borrador'], ['pendientes_publicacion', 'Pendientes de publicación']].map(([key, title]) => <section key={key}><h3>{title}</h3>{data[key]?.length ? <ul>{data[key].map((item) => <li key={item.id}><strong>{item.campo}: </strong>{item.motivo} <p>{item.condicion_resolucion}</p></li>)}</ul> : <p>No se identificaron pendientes en este grupo.</p>}</section>)}</>
}

export default function CrawlingProposal({ publication }) {
  const [list, setList] = useState(null)
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [draft, setDraft] = useState(null)
  const [source, setSource] = useState(null)
  const [documents, setDocuments] = useState([])
  const [institutions, setInstitutions] = useState([])
  const [countries, setCountries] = useState([])
  const [types, setTypes] = useState([])
  const [applied, setApplied] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [result, setResult] = useState(null)
  const [historical, setHistorical] = useState(null)
  const key = useRef(null)
  const sending = useRef(false)
  const heading = useRef(null)
  const path = `${prefix}/publicaciones/${publication}/propuesta`
  useEffect(() => {
    let live = true
    offersApi.get(path, { page }).then((data) => { if (live) { setList(data); setApplied(data.aplicacion || null); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [path, page, retry])

  async function evidence(context) {
    const version = await offersApi.get(`${prefix}/publicaciones/${publication}/versiones/${context.version_id}`)
    const docs = []; let p = 1; let response
    do {
      response = await offersApi.get(`${prefix}/publicaciones/${publication}/versiones/${context.version_id}/documentos`, { page: p, page_size: 50 })
      docs.push(...response.results); p += 1
    } while ((p - 1) * response.page_size < response.count)
    setSource(version); setDocuments(docs)
  }

  async function open() {
    setBusy(true); setError('')
    try {
      const latest = await offersApi.get(path)
      const entities = []; let n = 1; let response
      do {
        response = await offersApi.get('gestion/instituciones', { page: n, page_size: 50 })
        entities.push(...response.results); n += 1
      } while ((n - 1) * response.page_size < response.count)
      setInstitutions(entities)
      const catalogs = await offersApi.get('becas/catalogos')
      setCountries(catalogs.paises || [])
      setTypes(catalogs.tipos_requisito || [])
      setList(latest)
      if (!latest.contexto) throw new Error('No hay observación exitosa para preparar una propuesta.')
      const old = latest.results[0]
      const next = old ? { id: old.id, hash_propuesta: old.hash_propuesta, version_id: old.version_id, observacion_base_id: old.observacion_base_id, revisiones: old.revisiones, datos: old.datos, procedencia: old.procedencia } : { ...latest.contexto, datos: {}, procedencia: [] }
      await evidence(next)
      key.current = null; setDraft(next); setResult(old?.pendientes || null); setHistorical(null)
      setTimeout(() => heading.current?.focus(), 0)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function edit(next) { key.current = null; setDraft(next); setResult(null); setSuccess('') }
  async function refreshContext() {
    setBusy(true); setError('')
    try {
      const current = await offersApi.get(path)
      if (!current.contexto) throw new Error('Sin observación exitosa.')
      await evidence(current.contexto)
      setList(current)
      // No remapear referencias documentales entre versiones ni perder los valores pendientes.
      edit({ ...draft, ...current.contexto, id: current.results[0]?.id, hash_propuesta: current.results[0]?.hash_propuesta, procedencia: draft.version_id === current.contexto.version_id ? draft.procedencia : draft.procedencia.map((ref) => ({ ...ref, evidencia_id: '' })) })
      setSuccess('Contexto actualizado. Se conservaron los valores; revisa y vuelve a indicar la procedencia si cambió la versión.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function save(event) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true; setBusy(true); setError(''); setSuccess('')
    key.current ||= crypto.randomUUID()
    try {
      const body = { ...draft }
      delete body.id; delete body.hash_propuesta
      const saved = await offersApi.write(draft.id ? `${prefix}/propuestas/${draft.id}` : path, draft.id ? 'PATCH' : 'POST', { ...body, clave_accion: key.current })
      setDraft({ id: saved.id, hash_propuesta: saved.hash_propuesta, version_id: saved.version_id, observacion_base_id: saved.observacion_base_id, revisiones: saved.revisiones, datos: saved.datos, procedencia: saved.procedencia })
      key.current = null; setResult(saved.pendientes); setSuccess('Propuesta guardada fuera del catálogo. No se creó una convocatoria.'); setRetry((n) => n + 1)
    } catch (e) { setError(`${[...new Set([e.message, ...validationMessages(e.fields)])].join(' ')} Tus valores se conservan. ${e.status === 409 ? 'Consulta el historial y actualiza el contexto antes de volver a guardar.' : 'Corrige los datos o reintenta.'}`) } finally { sending.current = false; setBusy(false) }
  }

  async function validate() {
    setBusy(true); setError('')
    try {
      const data = await offersApi.write(`${prefix}/propuestas/${draft.id}/validar`, 'POST')
      setResult(data.actual); setSuccess(data.contexto_cambio ? 'El contexto cambió respecto del resultado guardado. El snapshot anterior se conserva.' : 'Validación actual del último snapshot guardado. Los cambios sin guardar no están incluidos.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return <section className="profile-card crawl-proposal"><h2 ref={heading} tabIndex={-1}>Propuesta de integración</h2><p>Trabajo administrativo fuera del catálogo. Guardar no crea ni publica una convocatoria.</p>
    {error && <Message>{error}</Message>}{success && <p role="status">{success}</p>}
    {!list && !error && <p role="status">Cargando propuestas…</p>}
    {error && !list && <Button onClick={() => setRetry((n) => n + 1)}>Reintentar</Button>}
    {applied && <p role="status">La publicación ya tiene un borrador vinculado. <a href={`/gestion/convocatorias/${applied.convocatoria_id}`}>Abrir convocatoria</a></p>}
    {list && !draft && !applied && <Button busy={busy} disabled={!list.contexto} onClick={open}>{list.count ? 'Continuar propuesta' : 'Crear propuesta'}</Button>}
    {draft && <form onSubmit={save}><fieldset disabled={busy}><legend>Datos de trabajo</legend><p>Publicación {publication} · Versión ID {draft.version_id} · Observación {draft.observacion_base_id}</p>
      <Button type="button" onClick={refreshContext}>Actualizar contexto conservando valores</Button>
      {source && <details><summary>Evidencia original de esta versión</summary><p>{source.datos_extraidos?.titulo?.texto_original}</p><p>{source.datos_extraidos?.descripcion?.texto_original}</p><p>Los documentos y la evidencia completa siguen disponibles arriba. No constituyen opciones ni requisitos confirmados.</p></details>}
      <div className="form-grid"><div className="field"><label htmlFor="propuesta-institucion">Entidad oferente</label><select id="propuesta-institucion" value={draft.datos.institucion || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, institucion: e.target.value ? Number(e.target.value) : null } })}><option value="">Pendiente de identificar</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select></div>{Object.entries({ titulo: 'Título propuesto', descripcion: 'Descripción propuesta', url_oficial: 'Enlace oficial', apertura_original: 'Apertura literal (sin inventar hora)', cierre_original: 'Cierre literal (sin inventar hora)' }).map(([name, label]) => <Field key={name} name={`propuesta-${name}`} label={label} value={draft.datos[name] ?? ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, [name]: e.target.value } })} />)}</div>
      {Object.entries(groups).map(([kind, label]) => <section key={kind}><h3>{label}</h3><p>Candidatos pendientes de interpretación; no se crean registros del catálogo.</p>{(draft.datos[kind] || []).map((item, index) => <fieldset key={item.id}><legend>{label} {index + 1}</legend><div className="form-grid">{Object.entries(fields[kind]).map(([name, title]) => <Field key={name} name={`${item.id}-${name}`} label={title} value={item[name] || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].map((v) => v.id === item.id ? { ...v, [name]: e.target.value } : v) } })} />)}</div>{kind === 'opciones' && <div className="field"><label htmlFor={`${item.id}-countries`}>Países candidatos de esta opción</label><select multiple id={`${item.id}-countries`} value={item.paises || []} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, opciones: draft.datos.opciones.map((v) => v.id === item.id ? { ...v, paises: Array.from(e.target.selectedOptions, (o) => o.value) } : v) } })}>{countries.map((country) => <option key={country.codigo} value={country.codigo}>{country.nombre}</option>)}</select><p>Selección explícita; no convierte las menciones originales en destinos confirmados.</p></div>}{kind !== 'opciones' && <Scope item={item} countries={countries} options={draft.datos.opciones || []} onChange={(next) => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].map((v) => v.id === item.id ? next : v) } })} />}<Button type="button" onClick={() => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].filter((v) => v.id !== item.id) } })}>Retirar candidato</Button></fieldset>)}<Button type="button" onClick={() => edit({ ...draft, datos: { ...draft.datos, [kind]: [...(draft.datos[kind] || []), { id: crypto.randomUUID(), texto: '', ambito: 'pendiente' }] } })}>Añadir {label.toLowerCase()}</Button></section>)}
      <h3>Procedencia y motivos</h3>{draft.procedencia.map((ref, i) => <fieldset key={i}><legend>Referencia {i + 1}</legend><label htmlFor={`evidence-${i}`}>Documento exacto</label><select id={`evidence-${i}`} required value={ref.evidencia_id || ''} onChange={(e) => edit({ ...draft, procedencia: draft.procedencia.map((v, j) => i === j ? { ...v, evidencia_id: Number(e.target.value) } : v) })}><option value="">Selecciona evidencia</option>{documents.map((doc) => <option key={doc.evidencia_id} value={doc.evidencia_id}>{doc.rol} · Relación {doc.id}</option>)}</select>{Object.entries({ campo: 'Campo o identificador del elemento', localizador: 'Página o sección', original: 'Texto original', motivo: 'Motivo de la transcripción o corrección' }).map(([name, title]) => <Field key={name} name={`ref-${i}-${name}`} label={title} value={ref[name] || ''} onChange={(e) => edit({ ...draft, procedencia: draft.procedencia.map((v, j) => i === j ? { ...v, [name]: e.target.value } : v) })} />)}<Button type="button" onClick={() => edit({ ...draft, procedencia: draft.procedencia.filter((_v, j) => i !== j) })}>Retirar referencia</Button></fieldset>)}<Button type="button" onClick={() => edit({ ...draft, procedencia: [...draft.procedencia, { campo: '', localizador: '', motivo: '' }] })}>Añadir referencia</Button>
      <div className="heading-actions"><Button type="submit" busy={busy}>Guardar propuesta</Button><Button type="button" disabled={!draft.id} onClick={validate}>Validar propuesta</Button></div></fieldset></form>}
    {draft?.id && !applied && result && <CrawlingDraft key={draft.id} proposal={draft} result={result} countries={countries} types={types} documents={documents} onCreated={(value) => { setApplied(value); setSuccess('Borrador creado y vinculado. Abriendo el editor administrativo.') }} />}
    {result && <Results data={result} />}
    {list?.count > 0 && <><h3>Historial inmutable</h3><ul>{list.results.map((row) => <li key={row.id}><Button onClick={() => setHistorical(row)}>Consultar revisión de propuesta {row.id}</Button> · {row.autor.nombre}</li>)}</ul>{list.count > list.page_size && <nav aria-label="Historial de propuestas"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={page * list.page_size >= list.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</>}
    {historical && <section><h3>Snapshot histórico {historical.id}</h3><p>{historical.datos.titulo || 'Sin título'}</p><p>{historical.datos.descripcion}</p><Results data={historical.pendientes} /><details><summary>Todos los valores históricos (solo lectura)</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(historical.datos, null, 2)}</pre></details></section>}
  </section>
}
