import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

const kinds = ['opciones', 'beneficios', 'requisitos']
const label = { opciones: 'Opción', beneficios: 'Beneficio', requisitos: 'Requisito' }
const levels = ['bachillerato', 'grado', 'especializacion', 'maestria', 'doctorado']
const modalities = ['presencial', 'virtual', 'semipresencial', 'hibrida']

function catalogData(kind, item, countries, types, extra) {
  const option = item.opcion || null
  const scope = item.ambito
  const baseScope = scope === 'comun' ? { opcion_estudio: null } : { opcion_estudio: option }
  if (kind === 'opciones') {
    if (!levels.includes(item.nivel) || !modalities.includes(item.modalidad) || !item.texto || !item.paises?.length) throw Error('Completa nivel, modalidad, programa y países en la propuesta antes de seleccionar esta opción.')
    const ids = item.paises.map((code) => countries.find((c) => c.codigo === code)?.id)
    if (ids.some((id) => !id)) throw Error('Un país ya no está en el catálogo. Actualiza el contexto.')
    return { nivel: item.nivel, modalidad: item.modalidad, programa: item.texto, paises: ids, activa: true }
  }
  if (!['comun', 'opcion', 'destino'].includes(scope) || (scope !== 'comun' && !option)) throw Error('Define el ámbito y su opción antes de seleccionar el elemento.')
  if (kind === 'beneficios') {
    if (!item.concepto) throw Error('Completa el concepto financiado antes de seleccionar este beneficio.')
    const number = (literal) => literal ? /^\d+(?:[.,]\d{1,2})?\s*%?$/.test(literal) ? Number(literal.replace('%', '').trim().replace(',', '.')) : (() => { throw Error('Cantidad literal ambigua; conserva el candidato pendiente.') })() : null
    if (scope === 'destino') throw Error('El beneficio por destino no tiene un ámbito equivalente en el modelo actual; conserva este candidato pendiente.')
    return { ...baseScope, concepto: item.concepto, porcentaje: number(item.porcentaje), monto: number(item.monto), moneda: item.monto ? item.moneda || null : null,
      tope_monto: null, tope_moneda: null, tope_original: item.tope || null,
      detalle: [item.texto, item.condiciones].filter(Boolean).join('\n') || null }
  }
  const type = types.find((t) => t.codigo === item.tipo)
  if (!type || !['DOCUMENTO', 'ACREDITACION', 'OTRO'].includes(type.codigo) || !item.texto) throw Error('Este requisito necesita mapeo estructurado adicional; consérvalo pendiente y revísalo en el editor.')
  const structured = type.codigo === 'DOCUMENTO' ? { documento: extra.nombre, condiciones: extra.condiciones || undefined } : type.codigo === 'ACREDITACION' ? { certificados_admitidos: extra.nombre, vigencia: extra.condiciones || undefined } : { descripcion: extra.nombre }
  if (!extra.nombre?.trim()) throw Error('Indica el nombre documental o descripción conforme a la evidencia.')
  return { ...baseScope, destino: scope === 'destino' ? item.destino : null, tipo_requisito: type.id,
    texto_original: item.texto, valor_estructurado: structured, modo_comprobacion: 'entidad_oferente',
    obligatorio: true, activo: true, validado: false, detalle_acreditacion: item.condiciones || null }
}

export default function CrawlingDraft({ proposal, result, countries, types = [], documents, onCreated }) {
  const navigate = useNavigate()
  const [selected, setSelected] = useState({})
  const [motives, setMotives] = useState({})
  const [extras, setExtras] = useState({})
  const [institutionReason, setInstitutionReason] = useState('')
  const [basesReason, setBasesReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const key = useRef(null)
  const all = kinds.flatMap((kind) => (proposal.datos[kind] || []).map((item) => ({ kind, item })))
  const pending = result?.pendientes_publicacion || []
  const blocked = Boolean(result?.bloqueos?.length)
  async function create() {
    if (busy) return
    setBusy(true); setError('')
    key.current ||= crypto.randomUUID()
    try {
      const payload = { clave_accion: key.current, hash_propuesta: proposal.hash_propuesta,
        observacion_base_id: proposal.observacion_base_id, revisiones: proposal.revisiones,
        motivo_institucion: institutionReason,
        confirmados: all.map(({ item }) => item.id), opciones: [], beneficios: [], requisitos: [] }
      if (basesReason.trim()) payload.motivo_bases_ausentes = basesReason
      for (const { kind, item } of all) if (selected[item.id]) {
        const values = catalogData(kind, item, countries, types, extras[item.id] || {})
        payload[kind].push({ id: item.id, datos: values, motivo: motives[item.id] || '' })
      }
      const response = await offersApi.write(`gestion/rastreo/propuestas/${proposal.id}/crear-borrador`, 'POST', payload)
      onCreated(response)
      navigate(`/gestion/convocatorias/${response.convocatoria_id}`)
    } catch (e) {
      const details = e.fields && typeof e.fields === 'object' ? JSON.stringify(e.fields) : ''
      setError(`${e.message} ${details} Los datos de confirmación se conservan; revisa el contexto o reintenta.`)
    } finally { setBusy(false) }
  }
  return <section className="crawl-draft" aria-label="Crear borrador vinculado">
    <h3>Crear borrador vinculado</h3><p>Crear exige revisiones vigentes y evidencia exacta. La convocatoria quedará en borrador; ningún requisito se validará automáticamente.</p>
    {blocked && <><p>Resuelve los bloqueos indicados antes de confirmar. La propuesta permanece guardada.</p><ul>{result.bloqueos.map((item) => <li key={item.id}>{item.motivo}</li>)}</ul></>}
    {error && <Message>{error}</Message>}
    <div className="field"><label htmlFor="draft-institution-reason">Correspondencia con la entidad oferente revisada</label><textarea id="draft-institution-reason" value={institutionReason} onChange={(e) => { key.current = null; setInstitutionReason(e.target.value) }} maxLength={2000} /></div>
    {!documents.some((d) => d.rol === 'bases_pdf') && <div className="field"><label htmlFor="draft-bases-reason">Ausencia real de bases identificadas</label><textarea id="draft-bases-reason" value={basesReason} onChange={(e) => { key.current = null; setBasesReason(e.target.value) }} maxLength={2000} /></div>}
    <h4>Contenido que se creará</h4><p>Institución, título, descripción y enlace oficial guardados en esta propuesta. Un día de cierre con evidencia y los topes literales se conservan sin inventar hora, moneda ni importe fijo. Permanecen pendientes hasta la revisión y resolución explícitas.</p>
    {all.map(({ kind, item }) => <fieldset key={item.id}><legend>{label[kind]}: {item.texto || item.concepto || item.id}</legend>
      <label className="crawl-check"><input type="checkbox" checked={Boolean(selected[item.id])} onChange={(e) => { key.current = null; setSelected({ ...selected, [item.id]: e.target.checked }) }} /> Incluir en el borrador</label>
      {!selected[item.id] ? <p>Permanecerá en la propuesta como pendiente de revisión o mapeo.</p> : <><div className="field"><label htmlFor={`motive-${item.id}`}>Motivo y respaldo del mapeo</label><textarea id={`motive-${item.id}`} value={motives[item.id] || ''} onChange={(e) => { key.current = null; setMotives({ ...motives, [item.id]: e.target.value }) }} maxLength={2000} /></div>
      {kind === 'requisitos' && <div className="form-grid"><div className="field"><label htmlFor={`docname-${item.id}`}>Nombre documental o descripción revisada</label><input id={`docname-${item.id}`} value={extras[item.id]?.nombre || ''} onChange={(e) => { key.current = null; setExtras({ ...extras, [item.id]: { ...extras[item.id], nombre: e.target.value } }) }} /></div><div className="field"><label htmlFor={`conditions-${item.id}`}>Condiciones documentales revisadas</label><input id={`conditions-${item.id}`} value={extras[item.id]?.condiciones || ''} onChange={(e) => { key.current = null; setExtras({ ...extras, [item.id]: { ...extras[item.id], condiciones: e.target.value } }) }} /></div></div>}</>}
    </fieldset>)}
    <h4>Pendientes materiales antes de publicar</h4>{pending.length ? <ul>{pending.map((item) => <li key={item.id}>{item.campo}: {item.motivo}</li>)}</ul> : <p>No se detectaron pendientes en la validación guardada; la creación volverá a comprobar el estado actual.</p>}
    <label className="crawl-check"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> Confirmo el contenido seleccionado y los elementos que permanecerán pendientes.</label>
    <Button type="button" busy={busy} disabled={busy || blocked || !confirmed || !institutionReason.trim()} onClick={create}>Crear borrador vinculado</Button>
  </section>
}
