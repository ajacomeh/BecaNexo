import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/context'
import Button from './Button'
import Message from './Message'

export default function EditName({ onClose, onSaved }) {
  const { user, updateName } = useAuth()
  const [name, setName] = useState(user.nombre)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const dialog = useRef(null)
  useEffect(() => {
    const element = dialog.current
    const trigger = document.activeElement
    element.showModal()
    return () => { element.close(); trigger?.focus() }
  }, [])
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    if (!name.trim()) { setError('El nombre no puede estar vacío.'); return }
    pending.current = true; setBusy(true); setError('')
    try { await updateName(name); onSaved() }
    catch (failure) { setError(failure.fields?.nombre?.join(' ') || failure.message) }
    finally { pending.current = false; setBusy(false) }
  }
  return <dialog ref={dialog} className="confirm-dialog name-dialog" aria-labelledby="name-title" aria-describedby="name-help" onCancel={e => { e.preventDefault(); if (!pending.current) onClose() }}>
    <h2 id="name-title">Editar nombre</h2><p id="name-help">Este nombre se muestra en tu cuenta. No modifica los datos de tu perfil académico</p>
    <form onSubmit={submit}><div className="field"><label htmlFor="visible-name">Nombre visible</label><input id="visible-name" value={name} onChange={e => setName(e.target.value)} required maxLength={180} disabled={busy} aria-invalid={Boolean(error)} aria-describedby={error ? 'name-error' : 'name-help'} /></div>
      {error && <div id="name-error"><Message>{error}</Message></div>}
      <div className="form-actions"><Button type="submit" busy={busy}>{busy ? 'Guardando…' : 'Guardar'}</Button><Button type="button" className="button-light" disabled={busy} onClick={onClose}>Cancelar</Button></div>
    </form>
  </dialog>
}
