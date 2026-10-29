import { useId, useState } from 'react'
import Button from './Button'
import { readable } from '../pages/catalogPresentation'

export default function CatalogFilters({ params, catalogs, onApply, onClear }) {
  const [values, setValues] = useState(() => Object.fromEntries(params))
  const id = useId()
  const secondary = ['tipo_beca', 'estado'].filter(key => params.get(key)).length
  function select(name, label, empty, rows) {
    return <div className="field" key={name}><label htmlFor={`${id}-${name}`}>{label}</label><select id={`${id}-${name}`} name={name} value={values[name] || ''} onChange={e => setValues({ ...values, [name]: e.target.value })}><option value="">{empty}</option>{rows.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></div>
  }
  return <section className="profile-card catalog-filters"><h2>Filtros de búsqueda</h2><form onSubmit={e => { e.preventDefault(); onApply(values) }}>
    <div className="catalog-filter-grid"><label className="field"><span>Buscar título, institución o área</span><input name="q" maxLength={200} value={values.q || ''} onChange={e => setValues({ ...values, q: e.target.value })} /></label>
      {select('nivel', 'Nivel', 'Todos los niveles', catalogs.niveles.map(r => [r.valor, r.nombre]))}
      {select('modalidad', 'Modalidad', 'Todas las modalidades', catalogs.modalidades.map(r => [r.valor, r.nombre]))}
      {select('destino', 'Destino de estudio', 'Todos los destinos', catalogs.paises.map(r => [r.codigo, r.nombre]))}
    </div>
    <details><summary>Más filtros{secondary > 0 && ` · ${secondary} aplicados`}</summary><div className="catalog-filter-grid">
      {select('tipo_beca', 'Tipo de beca', 'Todos los tipos', catalogs.tipos_beca.map(r => [r.id, r.nombre]))}
      {select('estado', 'Estado', 'Todos los estados', ['abierta', 'cerrada', 'proxima', 'sin_fecha'].map(v => [v, v === 'proxima' ? 'Próxima apertura' : v === 'sin_fecha' ? 'Fecha de cierre no informada' : readable(v)]))}
    </div></details>
    <div className="form-actions"><Button icon="search" type="submit">Aplicar filtros</Button><Button icon="clear" className="button-light" type="button" onClick={() => { setValues({}); onClear() }}>Limpiar filtros</Button></div>
  </form></section>
}
