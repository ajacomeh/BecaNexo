import { useEffect, useRef, useState } from 'react'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import Field from './Field'
import CrawlingDraft from './CrawlingDraft'
import { proposalPrefill } from './proposalPrefill'

const prefix = 'gestion/rastreo'
const applyFieldLabels = { titulo: 'Título', descripcion: 'Descripción', institucion: 'Entidad oferente',
  url_oficial: 'Enlace oficial', cierre_original: 'Cierre literal', cierre_dia: 'Día de cierre',
  tipo_beca: 'Tipo de beca', cobertura_tipo: 'Cobertura', gastos_no_cubiertos: 'Gastos no cubiertos',
  url_bases: 'Enlace de las bases', apertura: 'Apertura confirmada' }
const coverageOptions = [['total', 'Total'], ['parcial', 'Parcial'], ['mixta', 'Mixta'], ['no_especificada', 'No especificada']]
// La apertura se guarda como instante con zona horaria de Ecuador; sin hora confirmada se deja vacía.
const openingInput = (value) => (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) ? value.slice(0, 16) : '')
const openingValue = (input) => (input ? `${input}:00-05:00` : '')
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
  const [scholarshipTypes, setScholarshipTypes] = useState([])
  const [applied, setApplied] = useState(null)
  const [linkedOffer, setLinkedOffer] = useState(null)
  const [selectedFields, setSelectedFields] = useState([])
  const [applyReason, setApplyReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [result, setResult] = useState(null)
  const [historical, setHistorical] = useState(null)
  const key = useRef(null)
  const sending = useRef(false)
  const heading = useRef(null)
  const path = `${prefix}/publicaciones/${publication}/propuesta`
  const entityMention = source?.datos_extraidos?.entidad_html?.texto_original?.trim() || ''
  const normalizeEntity = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es').replace(/\s+/g, ' ').trim()
  const entityMatches = entityMention ? institutions.filter((item) => normalizeEntity(item.nombre) === normalizeEntity(entityMention)) : []
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
    return { version, docs }
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
      setScholarshipTypes(catalogs.tipos_beca || [])
      setList(latest)
      setLinkedOffer(latest.borrador_automatico_id
        ? await offersApi.get(`gestion/convocatorias/${latest.borrador_automatico_id}`) : null)
      if (!latest.contexto) throw new Error('No hay observación exitosa para preparar una propuesta.')
      const old = latest.results[0]
      const next = old ? { id: old.id, hash_propuesta: old.hash_propuesta, version_id: old.version_id, observacion_base_id: old.observacion_base_id, revisiones: old.revisiones, datos: old.datos, procedencia: old.procedencia } : { ...latest.contexto, datos: {}, procedencia: [] }
      const { version, docs } = await evidence(next)
      const prefill = proposalPrefill(version, docs, next.datos)
      const referenced = new Set(next.procedencia.map((ref) => ref.campo))
      key.current = null; setDraft({ ...next, datos: prefill.data, procedencia: [...next.procedencia, ...prefill.references.filter((ref) => !referenced.has(ref.campo))] }); setResult(old?.pendientes || null); setHistorical(null)
      setTimeout(() => heading.current?.focus(), 0)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function edit(next) { key.current = null; setDraft(next); setResult(null); setSuccess('') }
  async function refreshContext() {
    setBusy(true); setError('')
    try {
      const current = await offersApi.get(path)
      if (!current.contexto) throw new Error('Sin observación exitosa.')
      const { version, docs } = await evidence(current.contexto)
      setList(current)
      // No remapear referencias documentales entre versiones ni perder los valores pendientes.
      const references = draft.version_id === current.contexto.version_id ? draft.procedencia : draft.procedencia.map((ref) => ({ ...ref, evidencia_id: '' }))
      const prefill = proposalPrefill(version, docs, draft.datos)
      const referenced = new Set(references.map((ref) => ref.campo))
      edit({ ...draft, ...current.contexto, id: current.results[0]?.id, hash_propuesta: current.results[0]?.hash_propuesta,
        datos: prefill.data, procedencia: [...references, ...prefill.references.filter((ref) => !referenced.has(ref.campo))] })
      setSuccess('Contexto actualizado sin sobrescribir valores. Revisa la procedencia de esta versión antes de guardar.')
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
      key.current = null; setResult(saved.pendientes); setSuccess(linkedOffer
        ? 'Propuesta guardada. El borrador vinculado no se modificó.'
        : 'Propuesta guardada fuera del catálogo. No se creó una convocatoria.'); setRetry((n) => n + 1)
    } catch (e) { setError(`${[...new Set([e.message, ...validationMessages(e.fields)])].join(' ')} Tus valores se conservan. ${e.status === 409 ? 'Consulta el historial y actualiza el contexto antes de volver a guardar.' : 'Corrige los datos o reintenta.'}`) } finally { sending.current = false; setBusy(false) }
  }

  async function validate() {
    setBusy(true); setError('')
    try {
      const data = await offersApi.write(`${prefix}/propuestas/${draft.id}/validar`, 'POST')
      setResult(data.actual); setSuccess(data.contexto_cambio ? 'El contexto cambió respecto del resultado guardado. El snapshot anterior se conserva.' : 'Validación actual del último snapshot guardado. Los cambios sin guardar no están incluidos.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function applyToLinked(event) {
    event.preventDefault()
    if (busy || !draft?.id || !linkedOffer) return
    setBusy(true); setError(''); setSuccess('')
    try {
      const updated = await offersApi.write(`${prefix}/propuestas/${draft.id}/aplicar-borrador`, 'POST', {
        version_convocatoria: linkedOffer.version, hash_propuesta: draft.hash_propuesta,
        campos: selectedFields, motivo: applyReason,
      })
      setLinkedOffer(updated); setSelectedFields([]); setApplyReason('')
      setSuccess('Campos seleccionados incorporados con auditoría. Revisa el borrador antes de publicar.')
    } catch (e) { setError(`${e.message} Ningún valor de la propuesta se descarta.`) }
    finally { setBusy(false) }
  }

  return <section className="profile-card crawl-proposal"><h2 ref={heading} tabIndex={-1}>Propuesta de integración</h2><p>Trabajo administrativo fuera del catálogo. Guardar no crea ni publica una convocatoria.</p>
    {error && <Message>{error}</Message>}{success && <p role="status">{success}</p>}
    {!list && !error && <p role="status">Cargando propuestas…</p>}
    {error && !list && <Button onClick={() => setRetry((n) => n + 1)}>Reintentar</Button>}
    {applied && <p role="status">La publicación ya tiene un borrador vinculado. <a href={`/gestion/convocatorias/${applied.convocatoria_id}`}>Abrir convocatoria</a></p>}
    {list?.borrador_automatico_id && <p role="status">Borrador privado del rastreo vinculado. La propuesta puede revisarse y aplicarse por campos, sin crear otro borrador. <a href={`/gestion/convocatorias/${list.borrador_automatico_id}`}>Abrir convocatoria</a></p>}
    {list && !draft && !applied && <Button busy={busy} disabled={!list.contexto} onClick={open}>{list.count ? 'Continuar propuesta' : 'Crear propuesta'}</Button>}
    {draft && <form onSubmit={save}><fieldset disabled={busy}><legend>Datos de trabajo</legend><p>Publicación {publication} · Versión ID {draft.version_id} · Observación {draft.observacion_base_id}</p>
      <Button type="button" onClick={refreshContext}>Actualizar contexto conservando valores</Button>
      {entityMatches.length > 0 && <p className="small-note">Posible coincidencia de oferente por nombre: {entityMatches.map((item) => item.nombre).join(', ')}. Verifica antes de seleccionar.</p>}
      <div className="form-grid"><div className="field"><label htmlFor="propuesta-institucion">Entidad oferente</label><select id="propuesta-institucion" value={draft.datos.institucion || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, institucion: e.target.value ? Number(e.target.value) : null } })}><option value="">Pendiente de identificar</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select><small>Selecciona una entidad solo después de verificarla; la mención del portal no la confirma.</small></div>{Object.entries({ titulo: 'Título propuesto', descripcion: 'Descripción propuesta', url_oficial: 'Enlace oficial', apertura_original: 'Apertura literal (sin inventar hora)', cierre_original: 'Cierre literal (sin inventar hora)' }).map(([name, label]) => <Field key={name} name={`propuesta-${name}`} label={label} hint={{ titulo: 'Texto literal de la ficha HTML; revisa la referencia.', descripcion: 'Texto literal de la ficha HTML; revisa las bases.', url_oficial: 'Debe ser el enlace de postulación verificado, no la URL de publicación ni la de las bases.', cierre_original: 'Fecha literal de la ficha, sin hora inferida.' }[name]} value={draft.datos[name] ?? ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, [name]: e.target.value } })} />)}<div className="field"><label htmlFor="propuesta-cierre-dia">Día de cierre revisado, sin hora</label><input id="propuesta-cierre-dia" type="date" value={draft.datos.cierre_dia || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, cierre_dia: e.target.value } })} /><small>Día interpretado por el extractor a partir del texto literal; verifica la fecha y su referencia.</small></div>
        <div className="field"><label htmlFor="propuesta-tipo-beca">Tipo de beca</label><select id="propuesta-tipo-beca" value={draft.datos.tipo_beca || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, tipo_beca: e.target.value ? Number(e.target.value) : null } })}><option value="">Pendiente</option>{scholarshipTypes.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}</select></div>
        <div className="field"><label htmlFor="propuesta-cobertura">Cobertura según las bases</label><select id="propuesta-cobertura" value={draft.datos.cobertura_tipo || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, cobertura_tipo: e.target.value } })}><option value="">Pendiente</option>{coverageOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <Field name="propuesta-url_bases" label="Enlace de las bases" hint="Documento oficial de bases; no sustituye el enlace oficial de la convocatoria." value={draft.datos.url_bases ?? ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, url_bases: e.target.value } })} />
        <Field name="propuesta-gastos_no_cubiertos" label="Gastos no cubiertos" hint="Solo lo que las bases excluyen expresamente." value={draft.datos.gastos_no_cubiertos ?? ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, gastos_no_cubiertos: e.target.value } })} />
        <Field name="propuesta-apertura" type="datetime-local" label="Apertura con hora confirmada (America/Guayaquil)" hint="Déjala vacía si la fuente no indica la hora; conserva el literal en «Apertura literal»." value={openingInput(draft.datos.apertura)} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, apertura: openingValue(e.target.value) } })} /></div>
      {Object.entries(groups).map(([kind, label]) => <section key={kind}><h3>{label}</h3><p>Candidatos pendientes de interpretación; no se crean registros del catálogo.</p>{(draft.datos[kind] || []).map((item, index) => <fieldset key={item.id}><legend>{label} {index + 1}</legend><div className="form-grid">{Object.entries(fields[kind]).map(([name, title]) => <Field key={name} name={`${item.id}-${name}`} label={title} value={item[name] || ''} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].map((v) => v.id === item.id ? { ...v, [name]: e.target.value } : v) } })} />)}</div>{kind === 'opciones' && <div className="field"><label htmlFor={`${item.id}-countries`}>Países candidatos de esta opción</label><select multiple id={`${item.id}-countries`} value={item.paises || []} onChange={(e) => edit({ ...draft, datos: { ...draft.datos, opciones: draft.datos.opciones.map((v) => v.id === item.id ? { ...v, paises: Array.from(e.target.selectedOptions, (o) => o.value) } : v) } })}>{countries.map((country) => <option key={country.codigo} value={country.codigo}>{country.nombre}</option>)}</select><p>Selección explícita; no convierte las menciones originales en destinos confirmados.</p></div>}{kind !== 'opciones' && <Scope item={item} countries={countries} options={draft.datos.opciones || []} onChange={(next) => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].map((v) => v.id === item.id ? next : v) } })} />}<Button type="button" onClick={() => edit({ ...draft, datos: { ...draft.datos, [kind]: draft.datos[kind].filter((v) => v.id !== item.id) } })}>Retirar candidato</Button></fieldset>)}<Button type="button" onClick={() => edit({ ...draft, datos: { ...draft.datos, [kind]: [...(draft.datos[kind] || []), { id: crypto.randomUUID(), texto: '', ambito: 'pendiente' }] } })}>Añadir {label.toLowerCase()}</Button></section>)}
      <h3>Procedencia y motivos</h3><div className="crawl-reference-list">{draft.procedencia.map((ref, i) => {
        const document = documents.find((item) => item.evidencia_id === ref.evidencia_id)
        return <details key={i} className="crawl-reference"><summary>Referencia {i + 1} · {ref.campo || 'Campo pendiente'} · {document ? `${document.rol}, relación ${document.id}` : 'Documento pendiente'} · Versión {draft.version_id}</summary><fieldset><legend>Datos de la referencia {i + 1}</legend><label htmlFor={`evidence-${i}`}>Documento exacto</label><select id={`evidence-${i}`} required value={ref.evidencia_id || ''} onInvalid={(e) => { e.currentTarget.closest('details').open = true }} onChange={(e) => edit({ ...draft, procedencia: draft.procedencia.map((v, j) => i === j ? { ...v, evidencia_id: Number(e.target.value) } : v) })}><option value="">Selecciona evidencia</option>{documents.map((doc) => <option key={doc.evidencia_id} value={doc.evidencia_id}>{doc.rol} · Relación {doc.id}</option>)}</select>{Object.entries({ campo: 'Campo o identificador del elemento', localizador: 'Página o sección', original: 'Texto original', motivo: 'Motivo de la transcripción o corrección' }).map(([name, title]) => <Field key={name} name={`ref-${i}-${name}`} label={title} value={ref[name] || ''} onChange={(e) => edit({ ...draft, procedencia: draft.procedencia.map((v, j) => i === j ? { ...v, [name]: e.target.value } : v) })} />)}<Button type="button" onClick={() => edit({ ...draft, procedencia: draft.procedencia.filter((_v, j) => i !== j) })}>Retirar referencia</Button></fieldset></details>
      })}</div><Button type="button" onClick={() => edit({ ...draft, procedencia: [...draft.procedencia, { campo: '', localizador: '', motivo: '' }] })}>Añadir referencia</Button>
      <div className="heading-actions"><Button type="submit" busy={busy}>Guardar propuesta</Button><Button type="button" disabled={!draft.id} onClick={validate}>Validar propuesta</Button></div></fieldset></form>}
    {draft?.id && linkedOffer && result && <form onSubmit={applyToLinked}><h3>Aplicar cambios al borrador vinculado</h3><p>Selecciona únicamente los campos revisados. Los demás valores y opciones existentes permanecerán intactos.</p>
      {Object.entries(applyFieldLabels).filter(([name]) => draft.datos[name] != null && draft.datos[name] !== '').map(([name, label]) => <label key={name} className="field"><input type="checkbox" checked={selectedFields.includes(name)} onChange={(e) => setSelectedFields((old) => e.target.checked ? [...old, name] : old.filter((item) => item !== name))} />{label}: {String(linkedOffer[name]?.id ?? linkedOffer[name] ?? 'Pendiente')} → {String(name === 'tipo_beca' ? scholarshipTypes.find((item) => item.id === draft.datos[name])?.nombre ?? draft.datos[name] : draft.datos[name])}</label>)}
      <label className="field" htmlFor="proposal-apply-reason">Motivo de la aplicación</label><textarea id="proposal-apply-reason" required maxLength={1000} value={applyReason} onChange={(e) => setApplyReason(e.target.value)} />
      <Button type="submit" busy={busy} disabled={busy || !selectedFields.length}>Aplicar campos seleccionados</Button></form>}
    {draft?.id && !applied && !list?.borrador_automatico_id && result && <CrawlingDraft key={draft.id} proposal={draft} result={result} countries={countries} types={types} documents={documents} onCreated={(value) => { setApplied(value); setSuccess('Borrador creado y vinculado. Abriendo el editor administrativo.') }} />}
    {result && <Results data={result} />}
    {list?.count > 0 && <><h3>Historial inmutable</h3><ul>{list.results.map((row) => <li key={row.id}><Button onClick={() => setHistorical(row)}>Consultar revisión de propuesta {row.id}</Button> · {row.autor.nombre}</li>)}</ul>{list.count > list.page_size && <nav aria-label="Historial de propuestas"><Button disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={page * list.page_size >= list.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</>}
    {historical && <section><h3>Snapshot histórico {historical.id}</h3><p>{historical.datos.titulo || 'Sin título'}</p><p>{historical.datos.descripcion}</p><Results data={historical.pendientes} /><details><summary>Todos los valores históricos (solo lectura)</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(historical.datos, null, 2)}</pre></details></section>}
  </section>
}
