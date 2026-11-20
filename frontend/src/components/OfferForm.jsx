import { useRef, useState } from 'react'
import ProfileField from './ProfileField'
import Button from './Button'
import Message from './Message'
import EquivalenceFields from './EquivalenceFields'

const initialValue = (field, value) => {
  if (field.kind === 'equivalencias') return value || []
  if (field.multiple) return value || []
  if (field.kind === 'textos') return (value || []).join('\n')
  if (field.type === 'datetime-local' && value) return new Date(new Date(value).getTime() - 5 * 3600000).toISOString().slice(0, 16)
  return value == null ? '' : String(value)
}

export default function OfferForm({ icon = "save", fields, initial = {}, onSubmit, label = 'Guardar', onCancel }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((f) => [f.name, initialValue(f, initial[f.name])])))
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const change = (name, value) => { setValues((old) => ({ ...old, [name]: value })); setSaved(false) }
  async function submit(event) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setBusy(true); setError(''); setErrors({}); setSaved(false)
    const data = Object.fromEntries(fields.map((f) => {
      const v = values[f.name]
      let result = v
      if (f.kind === 'equivalencias') result = v
      else if (f.multiple) result = (v || []).map((x) => f.kind === 'ids' ? Number(x) : x)
      else if (v === '') result = f.required || f.blank ? '' : null
      else if (f.kind === 'boolean') result = v === 'true'
      else if (['id', 'number', 'integer'].includes(f.kind)) result = Number(v)
      else if (f.kind === 'textos') result = v.split('\n').map((x) => x.trim()).filter(Boolean)
      else if (f.type === 'datetime-local') result = `${v}:00-05:00`
      return [f.name, result]
    }))
    try { await onSubmit(data); setSaved(true) }
    catch (failure) { setError(failure.message); setErrors(failure.fields || {}) }
    finally { lock.current = false; setBusy(false) }
  }
  const renderField = (f) => f.kind === 'equivalencias' ? <EquivalenceFields key={f.name} field={f} values={values[f.name]} onChange={v => change(f.name, v)} disabled={busy} error={errors[f.name]} /> : f.multiple ? <fieldset className="field field-wide multi-field" key={f.name} disabled={busy}>
      <legend>{f.label}</legend><div className="multi-options">{f.options.map((o) => <label key={o.value}>
        <input type="checkbox" checked={(values[f.name] || []).map(String).includes(String(o.value))} onChange={(e) => change(f.name, e.target.checked ? [...values[f.name], String(o.value)] : values[f.name].filter((x) => String(x) !== String(o.value)))} />{o.label}</label>)}</div>
      {errors[f.name] && <p className="field-error">{String(errors[f.name])}</p>}
    </fieldset> : <ProfileField key={f.name} field={f} value={values[f.name]} disabled={busy} onChange={(v) => change(f.name, v)} error={errors[f.name]} />
  const supplementary = fields.filter(f => f.supplementary)
  return <form noValidate onSubmit={submit} aria-busy={busy}>
    <div className="field-grid">{fields.filter(f => !f.supplementary).map(renderField)}</div>
    {supplementary.length > 0 && <details open={supplementary.some(f => initial[f.name] || errors[f.name]) || undefined}>
      <summary>Información documental complementaria (opcional)</summary>
      <p className="field-hint">Conserva información adicional registrada en los campos generales del requisito. No repitas el nombre ni las condiciones principales; estos datos también se muestran al consultar la convocatoria.</p>
      <div className="field-grid">{supplementary.map(renderField)}</div>
    </details>}
    <Message>{error}</Message>{saved && <Message kind="success">Cambios guardados.</Message>}
    <div className="form-actions"><Button icon={icon} type="submit" busy={busy}>{busy ? 'Guardando…' : label}</Button>{onCancel && <Button icon="cancel" type="button" className="button-light" disabled={busy} onClick={onCancel}>Cancelar</Button>}</div>
  </form>
}
