import { useRef, useState } from 'react'
import ProfileField from './ProfileField'
import Message from './Message'
import Button from './Button'

export default function ProfileForm({ fields, initial = {}, onSubmit, onCancel, label = 'Guardar cambios' }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.name, initial[field.name] == null ? '' : String(initial[field.name])])))
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    pending.current = true
    setBusy(true); setMessage(null); setErrors({}); setSaved(false)
    const data = Object.fromEntries(fields.map((field) => {
      const value = values[field.name]
      return [field.name, value === '' ? (field.required ? '' : null) : field.kind === 'boolean' ? value === 'true' : field.kind === 'id' ? Number(value) : value]
    }))
    try { await onSubmit(data); setSaved(true) }
    catch (failure) { setMessage(failure.message); setErrors(failure.fields || {}) }
    finally { pending.current = false; setBusy(false) }
  }
  return <form noValidate onSubmit={submit} aria-busy={busy}>
    <div className="field-grid">{fields.map((field) => <ProfileField key={field.name} field={field} value={values[field.name]} disabled={busy}
      onChange={(value) => { setValues({ ...values, [field.name]: value }); setSaved(false) }} error={errors[field.name]} />)}</div>
    <Message>{message}</Message>
    {saved && <Message kind="success">Cambios guardados.</Message>}
    <div className="form-actions"><Button type="submit" busy={busy}>{busy ? 'Guardando…' : label}</Button>
      {onCancel && <Button type="button" className="button-light" disabled={busy} onClick={onCancel}>Cancelar</Button>}</div>
  </form>
}
