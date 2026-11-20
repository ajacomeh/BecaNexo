import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import './OriginPanel.css'

const path = (id) => `gestion/rastreo/convocatorias/${id}/origen`
const publicUrl = (value) => {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null } catch { return null }
}

function CandidateCard({ item, type, onPrepare }) {
  const origin = item.procedencia || {}
  const requirements = type === 'requisitos'
  const benefits = type === 'beneficios'
  const values = requirements ? Object.entries(item.valor_sugerido || {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`) : []
  const benefitValues = benefits ? [item.concepto_sugerido ? `Concepto literal: ${item.concepto_sugerido}` : 'Concepto por confirmar',
    item.porcentaje != null ? `Porcentaje literal: ${item.porcentaje}%` : 'Porcentaje por confirmar',
    item.monto != null ? `Importe fijo literal: ${item.monto} ${item.moneda}` : null,
    item.tope_original ? `Tope literal: ${item.tope_original}` : null].filter(Boolean) : []
  const canPrepare = !benefits || item.porcentaje != null || item.monto != null || item.tope_original
  return <li className="origin-candidate"><p className="origin-candidate-text">{requirements || benefits ? item.texto_original : `${item.nivel} · ${item.modalidad} · Destino declarado: ${item.destino_original}. Confirma país y agrupación.`}</p>
    {requirements && <div className="origin-candidate-meta"><span>Tipo: {item.tipo_sugerido || 'OTRO'}</span><span>Estado: {item.estado || 'pendiente'}</span><span>{item.metodo === 'regla' ? 'Condición literal' : item.metodo === 'onnx' ? 'Categoría sugerida por ONNX' : 'Clasificación pendiente'}</span></div>}
    {origin.version_id && <p className="origin-candidate-source">Versión {origin.version_id}{origin.documento_id && ` · Documento ${origin.documento_id}`}</p>}
    {requirements && values.length > 0 && <p className="origin-candidate-values"><strong>Valores propuestos:</strong> {values.join(' · ')}. Confirma los campos faltantes en las bases.</p>}
    {benefits && <p className="origin-candidate-values">{benefitValues.join(' · ')} · confirma concepto, alcance y condiciones</p>}
    {canPrepare && <div className="origin-candidate-action"><Button type="button" className="button-light" onClick={() => onPrepare(type, item)}>Preparar en editor</Button></div>}
  </li>
}

function TabularEvidence({ evidence }) {
  if (!evidence?.tablas?.length && !evidence?.enlaces_documentales?.length) return null
  return <details><summary>Tablas y anexos de la ficha para revisar</summary>
    <p>Las filas conservan su contexto original; ninguna condición queda validada automáticamente.</p>
    <ul className="origin-candidate-list">{evidence.tablas?.map((table, index) => <li key={index} className="origin-candidate">
      <h4>{table.titulo || table.encabezado || `Tabla ${index + 1}`}</h4>
      {table.titulo && table.encabezado && <p className="origin-candidate-source">Sección: {table.encabezado}</p>}
      <p className="origin-candidate-source">Versión {table.procedencia.version_id} · Documento {table.procedencia.documento_id}</p>
      <ul>{table.filas.map((row, rowIndex) => <li key={rowIndex}>{row.celdas.join(' · ')} <span className="small-note">({row.tipo}; {row.condicion}{row.fecha_sugerida ? `; fecha ${row.fecha_sugerida}` : ''})</span></li>)}</ul>
    </li>)}
    {!!evidence.enlaces_documentales?.length && <li className="origin-candidate"><h4>Enlaces documentales encontrados</h4><ul>{evidence.enlaces_documentales.map((link, index) => <li key={index}>{publicUrl(link.url) ? <a href={publicUrl(link.url)} target="_blank" rel="noopener noreferrer">{link.texto}</a> : link.texto} <span className="small-note">(por revisar)</span></li>)}</ul></li>}</ul>
  </details>
}

function PDFEvidence({ evidence }) {
  if (!evidence?.documentos?.length) return null
  return <details><summary>Bases PDF archivadas para revisar ({evidence.documentos.length})</summary>
    <p>Texto detectado por página; ninguna condición queda validada ni aplicada al borrador.</p>
    <ul className="origin-candidate-list">{evidence.documentos.map((document) => <li key={document.documento_id} className="origin-candidate">
      <h4>Documento {document.documento_id} · {document.estado.replaceAll('_', ' ')}</h4>
      <p className="origin-candidate-source">Versión {document.version_id}{document.total_paginas != null && ` · ${document.total_paginas} páginas`} · {publicUrl(document.url) ? <a href={publicUrl(document.url)} target="_blank" rel="noopener noreferrer">URL oficial asociada</a> : 'URL pendiente'}</p>
      {document.estado === 'sin_texto' && <p>PDF sin texto seleccionable; requiere revisión manual. No se aplicó OCR.</p>}
      {(document.fragmentos_truncados || document.paginas?.some((page) => page.texto_recortado) || document.estado === 'limite_paginas') && <p>Lectura parcial por límites de seguridad; revisa el PDF original.</p>}
      {!!document.fragmentos.length && <ul>{document.fragmentos.map((item, index) => <li key={index}>{item.texto_original} <span className="small-note">(p. {item.procedencia.pagina}; {item.tipo}; {item.condicion}{item.categoria ? `; ${item.categoria}` : ''})</span></li>)}</ul>}
    </li>)}</ul>
    {evidence.omitidos_por_limite && <p>Hay más documentos; se conserva el límite de tres PDF por consulta.</p>}
  </details>
}

function DocumentProposals({ proposals, onPrepare }) {
  if (!proposals?.length) return null
  return <details><summary>Propuestas documentales para revisar ({proposals.length})</summary>
    <p>Selecciona una propuesta para prepararla en el editor. Confirma su alcance y guarda el campo por separado; ninguna se valida ni publica aquí.</p>
    <ul className="origin-candidate-list">{proposals.map((item, index) => <li key={`${item.procedencia.documento_id}-${item.procedencia.pagina || item.procedencia.fila || 0}-${index}`} className="origin-candidate">
      <p className="origin-candidate-text">{item.texto_original}</p>
      <div className="origin-candidate-meta"><span>{item.campo}</span><span>Pendiente de revisión</span>{item.categoria && <span>Categoría: {item.categoria}</span>}{item.seccion && <span>Sección: {item.seccion}</span>}</div>
      <p className="origin-candidate-source">Documento {item.procedencia.documento_id} · Versión {item.procedencia.version_id}{item.procedencia.pagina && ` · p. ${item.procedencia.pagina}`}{item.procedencia.fila && ` · fila ${item.procedencia.fila}`}{publicUrl(item.procedencia.url) && <> · <a href={publicUrl(item.procedencia.url)} target="_blank" rel="noopener noreferrer">Origen oficial</a></>}</p>
      {!!item.advertencias?.length && <ul>{item.advertencias.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
      {item.destino && <div className="origin-candidate-action"><Button type="button" className="button-light" onClick={() => onPrepare(item.destino,
        item.destino === 'general' ? { campo: item.campo, valor: item.valor }
          : item.destino === 'requisitos' ? { texto_original: item.valor, tipo_sugerido: item.campo === 'documento exigido' ? 'DOCUMENTO' : 'OTRO', estado: 'pendiente', procedencia: item.procedencia }
            : { texto_original: item.valor, concepto_sugerido: item.valor, porcentaje: null, monto: null, procedencia: item.procedencia })}>Preparar en editor</Button></div>}
    </li>)}</ul>
  </details>
}

const preloadKinds = { requisitos: 'Requisito', beneficios: 'Beneficio', opciones: 'Opción de estudio' }
const preloadStates = { pendiente: 'Pendiente de revisión', aceptado: 'Aceptado', descartado: 'Descartado' }

function Preload({ offerId, version, rows, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const key = useRef(null)
  const pending = rows.filter((row) => row.estado === 'pendiente').length
  async function preload() {
    if (busy) return
    setBusy(true); setError(''); setResult(null)
    key.current ||= crypto.randomUUID()
    try {
      const response = await offersApi.write(`gestion/rastreo/convocatorias/${offerId}/precargar`, 'POST', { version_convocatoria: version, clave_accion: key.current })
      key.current = null; setResult(response); await onChanged()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function decide(row, decision) {
    if (busy) return
    setBusy(true); setError('')
    try {
      await offersApi.write(`gestion/rastreo/convocatorias/${offerId}/precarga/resolver`, 'POST', { modelo: row.modelo, id: row.id, decision, version_convocatoria: version })
      await onChanged()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return <section className="origin-preload" aria-labelledby="origin-preload-title"><h3 id="origin-preload-title">Propuestas precargadas</h3>
    <p>Crea en el borrador, como registros inactivos y sin validar, los requisitos, beneficios y opciones extraídos con confianza alta o media. Los ambiguos quedan para revisión manual. Nada se publica.</p>
    <Button type="button" busy={busy} disabled={busy} onClick={preload}>Precargar propuestas</Button>
    <Message>{error}</Message>
    {result && <p role="status">{result.creados.length ? `${result.creados.length === 1 ? 'Se creó 1 registro inactivo' : `Se crearon ${result.creados.length} registros inactivos`} para revisar.` : 'No hay propuestas nuevas para precargar.'}{result.omitidos.length > 0 && ` ${result.omitidos.length === 1 ? '1 candidato quedó' : `${result.omitidos.length} candidatos quedaron`} para revisión manual.`}</p>}
    {result?.omitidos?.length > 0 && <details><summary>Candidatos no precargados ({result.omitidos.length})</summary><ul>{result.omitidos.map((row) => <li key={row.huella}><strong>{preloadKinds[row.modelo]}:</strong> {row.texto} <span className="small-note">({row.motivo})</span></li>)}</ul></details>}
    {rows.length > 0 && <><p>{pending ? `${pending === 1 ? '1 pendiente' : `${pending} pendientes`} de revisión. Bloquean la publicación hasta que aceptes o descartes cada uno.` : 'Todas las propuestas precargadas están revisadas.'}</p>
      <ul className="origin-candidate-list">{rows.map((row) => <li key={`${row.modelo}-${row.id}`} className="origin-candidate">
        <p className="origin-candidate-text">{row.texto}</p>
        <div className="origin-candidate-meta"><span>{preloadKinds[row.modelo]}</span><span>Confianza {row.confianza}</span><span>{preloadStates[row.estado]}</span></div>
        {row.procedencia?.version_id && <p className="origin-candidate-source">Versión {row.procedencia.version_id}{row.procedencia.documento_id && ` · Documento ${row.procedencia.documento_id}`}{row.procedencia.campo && ` · Campo ${row.procedencia.campo}`}{row.procedencia.destino_original && ` · Destino literal: ${row.procedencia.destino_original}`}</p>}
        {row.estado === 'pendiente' && <div className="origin-candidate-action">
          <Button type="button" className="button-light" disabled={busy} onClick={() => decide(row, 'aceptar')}>{row.modelo === 'beneficios' ? 'Aceptar' : 'Aceptar y activar'}</Button>
          <Button type="button" className="button-light" disabled={busy} onClick={() => decide(row, 'descartar')}>{row.modelo === 'beneficios' ? 'Descartar y eliminar' : 'Descartar'}</Button>
        </div>}
      </li>)}</ul></>}
  </section>
}

export default function OriginPanel({ offer, onPrepare, onChanged }) {
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
  if (data?.automatico) return <section className="profile-card crawl-origin"><h2>Borrador generado por rastreo</h2>
    <p>Publicación {data.publicacion_id} · Versión {data.version_id}. Ninguna beca se publica automáticamente.</p>
    <Link to={`/gestion/rastreo/publicaciones/${data.publicacion_id}`}>Consultar ficha, versiones y documentos originales</Link>
    {data.cambio_relevante && <p role="status">La versión {data.version_actual_id} contiene cambios posteriores al borrador. Las ediciones administrativas se conservan.</p>}
    {data.cambio_relevante && !data.revision_confirmada && <form onSubmit={confirmVersion}><label htmlFor="origin-version-motive">Motivo de revisión de la nueva versión</label><textarea id="origin-version-motive" required maxLength={1000} value={motive} onChange={(e) => setMotive(e.target.value)} /><Button type="submit" disabled={busy} busy={busy}>Confirmar versión revisada</Button></form>}
    {error && <Message>{error}</Message>}{notice && <p role="status">{notice}</p>}
    <h3>Obligatorio antes de publicar</h3>{data.bloqueos_actuales.length ? <ul>{data.bloqueos_actuales.map((item) => <li key={item}>{item}</li>)}</ul> : <p>Los controles obligatorios de origen están completos. La publicación requiere confirmación administrativa.</p>}
    <Preload offerId={offer.id} version={data.version_convocatoria} rows={data.precarga || []}
      onChanged={async () => { setRetry((v) => v + 1); if (onChanged) await onChanged() }} />
    {!!data.observaciones?.length && <><h3>Datos complementarios por revisar</h3><ul>{data.observaciones.map((item) => <li key={item}>{item}</li>)}</ul></>}
    <h3>Evidencia y enlaces</h3><ul>
      <li>Publicación: {publicUrl(data.enlaces_origen?.publicacion) ? <a href={publicUrl(data.enlaces_origen.publicacion)} target="_blank" rel="noopener noreferrer">Abrir ficha de origen</a> : 'Sin enlace verificable'}</li>
      <li>Bases documentales: {data.enlaces_origen?.bases?.length ? data.enlaces_origen.bases.map((item, index) => <span key={index}>{index > 0 && ' · '}{publicUrl(item.url) ? <a href={publicUrl(item.url)} target="_blank" rel="noopener noreferrer">Bases {index + 1}</a> : 'Enlace pendiente de revisión'}</span>) : 'No identificadas'}</li>
      <li>Postulación externa: {data.enlaces_origen?.postulacion?.length ? data.enlaces_origen.postulacion.map((item, index) => <span key={index}>{index > 0 && ' · '}{publicUrl(item.url) ? <a href={publicUrl(item.url)} target="_blank" rel="noopener noreferrer">Postulación {index + 1}</a> : 'Enlace pendiente de revisión'}</span>) : 'No identificada; no usar la URL de la ficha como postulación'}</li>
    </ul>
    <details><summary>Requisitos extraídos para revisar ({data.candidatos_editables?.requisitos?.length || 0})</summary><ul className="origin-candidate-list">{data.candidatos_editables?.requisitos?.map((item, index) => <CandidateCard key={index} item={item} type="requisitos" onPrepare={onPrepare} />)}</ul></details>
    {!!data.candidatos_editables?.otros_campos?.beneficios?.length && <details><summary>Beneficios interpretados para revisar</summary><ul className="origin-candidate-list">{data.candidatos_editables.otros_campos.beneficios.map((item, index) => <CandidateCard key={index} item={item} type="beneficios" onPrepare={onPrepare} />)}</ul></details>}
    <details><summary>Opciones sugeridas para revisar ({data.candidatos_editables?.opciones?.length || 0})</summary><ul className="origin-candidate-list">{data.candidatos_editables?.opciones?.map((item, index) => <CandidateCard key={index} item={item} type="opciones" onPrepare={onPrepare} />)}</ul></details>
    {data.candidatos_editables?.otros_campos?.evidencia_tabular?.estado === 'no_disponible' && <p role="status">No se pudo verificar el HTML archivado para leer sus tablas; consulta los documentos de origen.</p>}
    <TabularEvidence evidence={data.candidatos_editables?.otros_campos?.evidencia_tabular} />
    <PDFEvidence evidence={data.candidatos_editables?.otros_campos?.evidencia_pdf} />
    <DocumentProposals proposals={data.candidatos_editables?.otros_campos?.propuestas_documentales} onPrepare={onPrepare} />
    <details><summary>Datos de origen conservados</summary><dl>{Object.entries(data.datos_iniciales).filter(([key, value]) => key !== 'candidatos_editables' && value).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{typeof value === 'object' ? `${value.nombre} (ID ${value.id}; confirmar antes de asignar)` : value}</dd></div>)}</dl></details>
  </section>
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
