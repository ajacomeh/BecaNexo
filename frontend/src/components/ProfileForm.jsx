import { useRef, useState } from 'react'
import ProfileField from './ProfileField'
import Message from './Message'
import Button from './Button'

export default function ProfileForm({ fields, initial = {}, onSubmit, onCancel, label = 'Guardar cambios', children }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.name,
    field.disabledWhen && initial[field.disabledWhen] === true ? '' : initial[field.name] == null ? (field.type === 'checkbox' ? 'false' : '') : String(initial[field.name])])) )
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const invalid = Object.fromEntries(fields.map(field => [field.name, field.validate?.(values[field.name])]).filter(([, error]) => error))
    if (Object.keys(invalid).length) { setErrors(invalid); setSaved(false); return }
    pending.current = true
    setBusy(true); setMessage(null); setErrors({}); setSaved(false)
    const data = Object.fromEntries(fields.map((field) => {
      const value = field.disabledWhen && values[field.disabledWhen] === 'true' ? '' : values[field.name]
      return [field.name, value === '' ? (field.required ? '' : null) : field.kind === 'boolean' ? value === 'true' : field.kind === 'id' ? Number(value) : value]
    }))
    try { await onSubmit(data); setSaved(true) }
    catch (failure) { setMessage(failure.message); setErrors(failure.fields || {}) }
    finally { pending.current = false; setBusy(false) }
  }
  return <form noValidate onSubmit={submit} aria-busy={busy}>
    <div className="field-grid">{children}{fields.map((field) => {
      const inactive = field.disabledWhen && values[field.disabledWhen] === 'true'
      return <ProfileField key={field.name} field={inactive ? { ...field, hint: field.disabledHint } : field} value={values[field.name]} disabled={busy || inactive}
        onChange={(value) => {
          const error = field.validate?.(value)
          setErrors(current => ({ ...current, [field.name]: error }))
          setSaved(false)
          if (error && value !== '') return
          setValues(current => {
            const next = { ...current, [field.name]: value }
            if (value === 'true') fields.filter(f => f.disabledWhen === field.name).forEach(f => { next[f.name] = '' })
            return next
          })
          setSaved(false)
        }} error={errors[field.name]} />
    })}</div>
    <Message>{message}</Message>
    {saved && <Message kind="success">Cambios guardados.</Message>}
    <div className="form-actions"><Button icon="save" type="submit" busy={busy}>{busy ? 'Guardando…' : label}</Button>
      {onCancel && <Button icon="cancel" type="button" className="button-light" disabled={busy} onClick={onCancel}>Cancelar</Button>}</div>
  </form>
}
