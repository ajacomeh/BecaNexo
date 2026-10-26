export default function EquivalenceFields({ field, values, onChange, disabled, error }) {
  const update = (index, key, value) => onChange(values.map((row, i) => i === index ? { ...row, [key]: value || null } : row))
  return <fieldset className="field field-wide multi-field" disabled={disabled}>
    <legend>{field.label}</legend><p className="profile-note">Registra solo equivalencias respaldadas por las bases. Los nombres de destino deben estar admitidos en este requisito. Las ciudades requieren país y provincia canónica.</p>
    {values.map((row, index) => <fieldset key={index} className="multi-field"><legend>Equivalencia {index + 1}</legend><div className="field-grid">
      <label>Tipo<select value={row.tipo} onChange={e => update(index, 'tipo', e.target.value)}>{(field.codigo === 'TITULO_AREA' ? ['titulo'] : ['provincia', 'ciudad']).map(t => <option key={t}>{t}</option>)}</select></label>
      {['origen', 'admitido', 'referencia'].map(key => <label key={key}>{ { origen: 'Nombre declarado equivalente', admitido: 'Nombre admitido en las bases', referencia: 'Referencia que respalda la equivalencia' }[key]}<input value={row[key] || ''} maxLength={1000} onChange={e => update(index, key, e.target.value)} /></label>)}
      {field.codigo === 'RESIDENCIA' && <><label>País del contexto<select value={row.pais || ''} onChange={e => update(index, 'pais', e.target.value)}><option value="">Selecciona</option>{field.paises.map(p => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}</select></label><label>Provincia canónica (solo ciudades)<input value={row.provincia || ''} onChange={e => update(index, 'provincia', e.target.value)} /></label></>}
    </div><button type="button" className="text-button danger-text" onClick={() => onChange(values.filter((_, i) => i !== index))}>Quitar equivalencia {index + 1}</button></fieldset>)}
    <button type="button" className="text-button" onClick={() => onChange([...values, { tipo: field.codigo === 'TITULO_AREA' ? 'titulo' : 'provincia', origen: '', admitido: '', referencia: '', pais: null, provincia: null }])}>Añadir equivalencia</button>
    {error && <p role="alert" className="field-error">{String(error)}</p>}
  </fieldset>
}
