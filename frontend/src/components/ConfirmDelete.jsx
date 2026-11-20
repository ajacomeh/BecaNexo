import { useEffect, useRef, useState } from 'react'
import Button from './Button'
import Message from './Message'

export default function ConfirmDelete({ title, heading, children, onConfirm, onCancel, description = 'Este registro se quitará de tu perfil. Esta acción no se puede deshacer.' }) {
  const dialog = useRef(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => { dialog.current.showModal() }, [])
  async function remove() {
    if (busy) return
    setBusy(true)
    try { await onConfirm() } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <dialog ref={dialog} className="confirm-dialog" aria-labelledby="delete-title" onCancel={(event) => { event.preventDefault(); if (!busy) onCancel() }}>
    <h2 id="delete-title">{heading || `¿Eliminar ${title}?`}</h2><p>{description}</p>{children}
    <Message>{error}</Message><div className="form-actions">
      <Button icon="delete" className="button-danger" busy={busy} onClick={remove}>Confirmar eliminación</Button>
      <Button icon="cancel" className="button-light" disabled={busy} onClick={onCancel}>Cancelar</Button>
    </div>
  </dialog>
}
