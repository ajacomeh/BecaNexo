export default function Field({ label, name, error, hint, ...props }) {
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <input id={name} name={name} aria-invalid={Boolean(error)}
        aria-describedby={error ? `${name}-error` : hint ? `${name}-hint` : undefined} {...props} />
      {hint && !error && <p className="field-hint" id={`${name}-hint`}>{hint}</p>}
      {error && <p className="field-error" id={`${name}-error`}>{Array.isArray(error) ? error.join(' ') : error}</p>}
    </div>
  )
}
