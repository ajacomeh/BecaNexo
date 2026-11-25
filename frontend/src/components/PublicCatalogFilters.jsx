import { useEffect, useId, useRef, useState } from 'react'
import Icon from './Icon'
import { AMBITOS, PUBLIC_FILTER_KEYS, activeFilters } from './publicCatalogFilterState'

// Filtros del catálogo público: se aplican al instante (la búsqueda, al dejar de escribir o con Enter).
// La gestión de convocatorias del administrador conserva su propio componente (CatalogFilters).
const SEARCH_DELAY = 400
// «Tipo de beca» queda oculto en el catálogo público hasta que haya datos; el parámetro sigue en la API y en la URL.
const SHOW_SCHOLARSHIP_TYPE = false

// Solo valores presentes según las facetas del servidor, con su número de resultados; el valor elegido se conserva
// aunque no tenga resultados. Sin facetas (respuesta antigua o aún sin datos) se muestran todos los valores.
function facetRows(all, facet, selected) {
  if (!facet) return all.map(([value, label]) => [value, label])
  const totals = new Map(facet.map(row => [String(row.valor), row.total]))
  return all.filter(([value]) => totals.has(String(value)) || String(value) === selected)
    .map(([value, label]) => [value, `${label} (${totals.get(String(value)) ?? 0})`])
}

export default function PublicCatalogFilters({ params, catalogs, facets, onChange }) {
  const id = useId()
  const urlQuery = params.get('q') || ''
  const [text, setText] = useState(urlQuery)
  const [seenQuery, setSeenQuery] = useState(urlQuery)
  const [open, setOpen] = useState(false)
  const searchRef = useRef(null)
  // Quitar una ficha o limpiar todo retira el botón pulsado: el foco pasa al buscador para no perderlo.
  const remove = changes => {
    if ('q' in changes) setText('')  // también descarta una búsqueda escrita que aún no se aplicó
    onChange(changes)
    searchRef.current?.focus()
  }
  // Si la búsqueda cambia desde fuera (una ficha, «Limpiar todo», la URL), el campo la refleja.
  if (urlQuery !== seenQuery) {
    setSeenQuery(urlQuery)
    if (text.trim() !== urlQuery) setText(urlQuery)
  }
  useEffect(() => {
    if (text.trim() === urlQuery) return undefined
    const timer = setTimeout(() => onChange({ q: text.trim() }), SEARCH_DELAY)
    return () => clearTimeout(timer)
  }, [text, urlQuery, onChange])
  const chips = activeFilters(params, catalogs)
  const value = key => params.get(key) || ''
  const ambito = value('destino_ambito')
  function select(name, label, empty, rows) {
    return <div className="catalog-filter-field" key={name}><label htmlFor={`${id}-${name}`}>{label}</label>
      <select id={`${id}-${name}`} name={name} value={value(name)} onChange={e => onChange(name === 'destino' ? { destino: e.target.value, destino_ambito: '' } : { [name]: e.target.value })}>
        <option value="">{empty}</option>{rows.map(([v, text]) => <option key={v} value={v}>{text}</option>)}</select></div>
  }
  const ambitoTotal = key => facets?.destino_ambito?.[key]
  return <section className="profile-card catalog-filters public-filters" role="search" aria-label="Filtros del catálogo">
    <form className="catalog-search" onSubmit={e => { e.preventDefault(); onChange({ q: text.trim() }) }}>
      <label htmlFor={`${id}-q`} className="visually-hidden">Buscar título, institución, área, descripción o programa</label>
      <Icon name="search" />
      <input ref={searchRef} id={`${id}-q`} name="q" type="search" maxLength={200} value={text} placeholder="Buscar por título, institución, área o programa" onChange={e => setText(e.target.value)} />
    </form>
    <button type="button" className="catalog-filters-toggle" aria-expanded={open} aria-controls={`${id}-controles`} onClick={() => setOpen(!open)}>
      <Icon name="preferences" /><span>Filtros ({chips.length})</span></button>
    <div id={`${id}-controles`} className={`catalog-filter-controls${open ? ' is-open' : ''}`}>
      {select('nivel', 'Nivel', 'Todos los niveles', facetRows((catalogs.niveles_opcion || catalogs.niveles).map(r => [r.valor, r.nombre]), facets?.nivel, value('nivel')))}
      {select('modalidad', 'Modalidad', 'Todas las modalidades', facetRows(catalogs.modalidades.map(r => [r.valor, r.nombre]), facets?.modalidad, value('modalidad')))}
      {select('destino', 'Destino de estudio', 'Todos los destinos', facetRows(catalogs.paises.map(r => [r.codigo, r.nombre]), facets?.destino, value('destino')))}
      {SHOW_SCHOLARSHIP_TYPE && select('tipo_beca', 'Tipo de beca', 'Todos los tipos', catalogs.tipos_beca.map(r => [r.id, r.nombre]))}
      <div className="catalog-filter-field"><span id={`${id}-ambito`}>Destino rápido</span>
        {/* Elección única: radios nativos (flechas del teclado) con aspecto de control segmentado. */}
        <div className="catalog-segmented" role="radiogroup" aria-labelledby={`${id}-ambito`}>
          {AMBITOS.map(([key, label]) => <label key={key || 'todos'} className={ambito === key ? 'is-checked' : undefined}>
            <input type="radio" className="visually-hidden" name={`${id}-destino-ambito`} value={key} checked={ambito === key}
              onChange={() => onChange({ destino_ambito: key, destino: '' })} />
            {key && ambitoTotal(key) != null ? `${label} (${ambitoTotal(key)})` : label}</label>)}
        </div></div>
      <div className="catalog-switch"><label htmlFor={`${id}-incluir`}>
        <input id={`${id}-incluir`} type="checkbox" role="switch" name="incluir_no_ecuatorianas" aria-describedby={`${id}-incluir-ayuda`}
          checked={value('incluir_no_ecuatorianas') === '1'} onChange={e => onChange({ incluir_no_ecuatorianas: e.target.checked ? '1' : '' })} />
        <span>Incluir entidades no ecuatorianas</span></label>
        <small id={`${id}-incluir-ayuda`}>Por defecto se muestran solo becas de entidades ecuatorianas.</small></div>
    </div>
    {chips.length > 0 && <div className="catalog-chips"><ul aria-label="Filtros activos">
      {chips.map(chip => <li key={chip.key}><span>{chip.label}</span><button type="button" aria-label={`Quitar filtro ${chip.label}`}
        onClick={() => remove({ [chip.key]: '' })}><Icon name="cancel" /></button></li>)}
    </ul><button type="button" className="catalog-clear-all" onClick={() => remove(Object.fromEntries(PUBLIC_FILTER_KEYS.map(k => [k, ''])))}>Limpiar todo</button></div>}
  </section>
}
