import { useId } from 'react'

export default function ProfileField({ field, value, onChange, error, disabled }) {
  const id = useId()
  const common = { id, name: field.name, value: value ?? '', onChange: (event) => onChange(event.target.value),
    disabled, required: field.required, 'aria-invalid': Boolean(error),
    'aria-describedby': [error && `${id}-error`, field.hint && `${id}-hint`, field.counter && `${id}-count`].filter(Boolean).join(' ') || undefined }
  if (field.type === 'checkbox') return <div className="field multi-field">
    <label className="multi-options" htmlFor={id}><input {...common} type="checkbox" checked={value === 'true'}
      onChange={event => onChange(String(event.target.checked))} /> {field.label}</label>
    {error && <p className="field-error" id={`${id}-error`}>{Array.isArray(error) ? error.join(' ') : error}</p>}
  </div>
  return <div className={`field ${field.wide ? 'field-wide' : ''}`}>
    <label htmlFor={id}>{field.label}{field.required && <span aria-hidden="true"> *</span>}</label>
    {field.options ? <select {...common}>
      <option value="">{field.placeholder || (field.required ? 'Selecciona una opción' : 'Sin declarar')}</option>
      {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select> : field.type === 'textarea' ? <textarea {...common} rows={3} maxLength={field.maxLength} /> :
      <input {...common} type={field.type || 'text'} step={field.type === 'number' ? '0.001' : undefined} maxLength={field.maxLength} />}
    {field.hint && <p className="field-hint" id={`${id}-hint`}>{field.hint}</p>}
    {field.counter && <p className="field-hint" id={`${id}-count`}>{(value || '').length} / {field.maxLength} caracteres</p>}
    {error && <p className="field-error" id={`${id}-error`}>{Array.isArray(error) ? error.join(' ') : error}</p>}
  </div>
}
