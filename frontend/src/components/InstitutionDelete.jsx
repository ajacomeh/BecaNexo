import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from './Button'
import Icon from './Icon'
import Message from './Message'

const plural = (n, singular, plural_) => `${n} ${n === 1 ? singular : plural_}`
const blockedText = (name, n) => `${name} tiene ${plural(n, 'convocatoria', 'convocatorias')} en el catálogo público. Despublícalas o reasígnalas a otra entidad antes de eliminarla.`

// Un solo diálogo (<dialog>, como el resto de confirmaciones) con dos modos:
// «No se puede eliminar esta entidad» (solo «Entendido») o la confirmación «Eliminar entidad oferente».
// El servidor es la autoridad: un 409 al confirmar cambia el diálogo al modo de bloqueo con su mensaje.
export default function InstitutionDelete({ entity, onClose, onDeleted }) {
  const dialog = useRef(null)
  const primary = useRef(null)
  const deleted = useRef(false)
  const [blocked, setBlocked] = useState(entity.convocatorias_publicas > 0 ? { n: entity.convocatorias_publicas, sample: null, message: '' } : null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const needsSample = Boolean(blocked && blocked.sample === null)
  const confirming = blocked === null

  useEffect(() => {
    const element = dialog.current
    const trigger = document.activeElement
    if (typeof element.showModal === 'function') element.showModal(); else element.setAttribute('open', '')
    // Al cerrar, el foco vuelve al botón de la fila (salvo si la entidad se eliminó: la página lo lleva al aviso).
    return () => { if (!deleted.current && trigger?.isConnected) trigger.focus() }
  }, [])
  useEffect(() => { primary.current?.focus() }, [confirming]) // el foco entra al diálogo y sigue al cambiar de modo
  useEffect(() => {
    if (!needsSample) return undefined
    let live = true
    // Consulta puntual, solo al abrir el modo de bloqueo: títulos de hasta 5 convocatorias públicas.
    offersApi.get(`gestion/instituciones/${entity.id}`)
      .then((data) => { if (live) setBlocked((old) => ({ ...old, n: data.convocatorias_publicas || old.n, sample: data.muestra_publicas || [] })) })
      .catch(() => { if (live) setBlocked((old) => ({ ...old, sample: [] })) })
    return () => { live = false }
  }, [needsSample, entity.id])

  const close = () => { if (!busy) onClose() }
  async function confirm() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const result = await offersApi.write(`gestion/instituciones/${entity.id}`, 'DELETE')
      deleted.current = true
      onDeleted(result || {})
    } catch (failure) {
      if (failure.status === 409) {
        const fields = failure.fields || {}
        setBlocked({ n: fields.convocatorias_publicas || 0, sample: fields.muestra_publicas || [], message: failure.message })
      } else setError(failure.message)
    } finally { setBusy(false) }
  }

  const drafts = entity.borradores_privados || 0
  return <dialog ref={dialog} className="confirm-dialog institution-delete-dialog" aria-labelledby="institution-delete-title" aria-describedby="institution-delete-text"
    onCancel={(event) => { event.preventDefault(); close() }} onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); close() } }}>
    {blocked ? <>
      <h2 id="institution-delete-title">No se puede eliminar esta entidad</h2>
      <div id="institution-delete-text"><p>{blocked.message || blockedText(entity.title, blocked.n)}</p></div>
      {blocked.sample === null ? <p role="status"><Icon name="loading" />Cargando convocatorias públicas…</p>
        : blocked.sample.length > 0 && <ul className="institution-delete-list" aria-label="Convocatorias en el catálogo público">
          {blocked.sample.map((c) => <li key={c.id}><Link to={`/gestion/convocatorias/${c.id}`}>{c.titulo}</Link></li>)}
          {blocked.n > blocked.sample.length && <li className="small-note">y {plural(blocked.n - blocked.sample.length, 'más', 'más')}</li>}
        </ul>}
      <div className="form-actions"><Button ref={primary} icon="success" type="button" onClick={close}>Entendido</Button></div>
    </> : <>
      <h2 id="institution-delete-title">Eliminar entidad oferente</h2>
      <div id="institution-delete-text"><p>¿Seguro que quieres eliminar {entity.title}? Esta acción no se puede deshacer.</p>
        {drafts > 0 && <p>{plural(drafts, 'borrador', 'borradores')} {drafts === 1 ? 'quedará' : 'quedarán'} sin entidad y {drafts === 1 ? 'pasará' : 'pasarán'} a «Oferente por confirmar».</p>}</div>
      <Message>{error}</Message>
      <div className="form-actions">
        <Button icon="delete" className="button-danger" type="button" busy={busy} onClick={confirm}>Sí, eliminar</Button>
        <Button ref={primary} icon="cancel" className="button-light" type="button" disabled={busy} onClick={close}>Cancelar</Button>
      </div>
    </>}
  </dialog>
}
