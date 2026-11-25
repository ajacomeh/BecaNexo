import { useId, useState } from 'react'
import Button from './Button'
import { readable } from '../pages/catalogPresentation'

export default function CatalogFilters({ params, catalogs, onApply, onClear, stateValues = ['abierta', 'cierre_hoy', 'cerrada', 'proxima', 'sin_fecha'], activeCount = null, allStateLabel = 'Todos los estados', showState = true, providerToggle = false }) {
  const [values, setValues] = useState(() => Object.fromEntries(params))
  const id = useId()
  // El catálogo público elige el estado con sus pestañas; aquí solo lo muestra la gestión de convocatorias.
  const secondary = (showState ? ['tipo_beca', 'estado'] : ['tipo_beca']).filter(key => params.get(key)).length
  function select(name, label, empty, rows) {
    return <div className="field" key={name}><label htmlFor={`${id}-${name}`}>{label}</label><select id={`${id}-${name}`} name={name} value={values[name] || ''} onChange={e => setValues({ ...values, [name]: e.target.value })}><option value="">{empty}</option>{rows.map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></div>
  }
  return <section className="profile-card catalog-filters"><h2>Filtros de búsqueda</h2>{activeCount !== null && <p className="catalog-filter-status" role="status">{activeCount === 0 ? 'Sin filtros activos' : `${activeCount} ${activeCount === 1 ? 'filtro activo' : 'filtros activos'}`}</p>}<form onSubmit={e => { e.preventDefault(); onApply(values) }}>
    <div className="catalog-filter-grid"><label className="field"><span>Buscar título, institución, área, descripción o programa</span><input name="q" maxLength={200} value={values.q || ''} onChange={e => setValues({ ...values, q: e.target.value })} /></label>
      {select('nivel', 'Nivel', 'Todos los niveles', (catalogs.niveles_opcion || catalogs.niveles).map(r => [r.valor, r.nombre]))}
      {select('modalidad', 'Modalidad', 'Todas las modalidades', catalogs.modalidades.map(r => [r.valor, r.nombre]))}
      {select('destino', 'Destino de estudio', 'Todos los destinos', catalogs.paises.map(r => [r.codigo, r.nombre]))}
    </div>
    {/* Solo en el catálogo público: incluir becas sin entidad oferente ecuatoriana asignada. */}
    {providerToggle && <div className="field catalog-provider-toggle"><label htmlFor={`${id}-incluir`}><input id={`${id}-incluir`} type="checkbox" name="incluir_no_ecuatorianas"
      aria-describedby={`${id}-incluir-ayuda`} checked={values.incluir_no_ecuatorianas === '1'}
      onChange={e => setValues({ ...values, incluir_no_ecuatorianas: e.target.checked ? '1' : '' })} />Incluir becas de entidades no ecuatorianas o sin confirmar</label>
      <p id={`${id}-incluir-ayuda`} className="field-hint">Por defecto se muestran solo becas de entidades ecuatorianas.</p></div>}
    <details><summary>Más filtros{secondary > 0 && ` · ${secondary} aplicados`}</summary><div className="catalog-filter-grid">
      {select('tipo_beca', 'Tipo de beca', 'Todos los tipos', catalogs.tipos_beca.map(r => [r.id, r.nombre]))}
      {showState && select('estado', 'Estado', allStateLabel, stateValues.map(v => [v, v === 'todas' ? 'Todas las publicadas' : v === 'vigentes' ? 'Vigentes' : v === 'proxima' ? 'Próxima apertura' : v === 'cierre_hoy' ? 'Cierra hoy; hora no informada' : v === 'sin_fecha' ? 'Fecha de cierre no informada' : readable(v)]))}    </div></details>
    <div className="form-actions"><Button icon="search" type="submit">Aplicar filtros</Button><Button icon="clear" className="button-light" type="button" onClick={() => { setValues({}); onClear() }}>Limpiar filtros</Button></div>
  </form></section>
}
