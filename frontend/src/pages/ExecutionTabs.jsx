import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { offersApi } from '../api/client'
import Button from '../components/Button'
import Icon from '../components/Icon'
import Message from '../components/Message'

// Detalle de ejecución: una sola lista visible (Accesos o Incidencias), 25 filas por página.
export const PAGE_SIZE = 25
const prefix = 'gestion/rastreo'
const gravityOptions = [['', 'Todas'], ['error', 'Error'], ['aviso', 'Aviso']]
const hour = (value) => value ? new Date(value).toLocaleTimeString('es-EC') : '—'

function safeUrl(url) {
  try {
    const parsed = new URL(url)
    return ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password
  } catch { return false }
}

function useRemote(path, params) {
  const [state, setState] = useState({ loading: true })
  const [retry, setRetry] = useState(0)
  const query = JSON.stringify(params)
  useEffect(() => {
    let live = true
    offersApi.get(`${prefix}/${path}`, JSON.parse(query))
      .then((data) => { if (live) setState({ data }) })
      .catch((error) => { if (live) setState({ error: error.message }) })
    return () => { live = false }
  }, [path, query, retry])
  return [state, () => { setState({ loading: true }); setRetry((value) => value + 1) }]
}

function Loading({ state, reload, children }) {
  if (state.error) return <><Message>{state.error}</Message><Button icon="refresh" type="button" onClick={reload}>Reintentar</Button></>
  if (state.loading) return <p role="status"><Icon name="loading" />Cargando información de rastreo…</p>
  return children(state.data)
}

// Paginador solo cuando hay más de una página: «1–25 de N».
export function Pager({ data, page, setPage, label }) {
  if (data.count <= data.page_size) return <p className="crawl-count">{data.count} {data.count === 1 ? 'registro' : 'registros'}</p>
  const first = (page - 1) * data.page_size + 1
  const last = Math.min(page * data.page_size, data.count)
  return <nav className="pagination" aria-label={`Paginación de ${label}`}>
    <Button icon="previous" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button>
    <span aria-live="polite">{first}–{last} de {data.count}</span>
    <Button icon="next" disabled={last >= data.count} onClick={() => setPage(page + 1)}>Siguiente</Button>
  </nav>
}

function Accesses({ execution, label }) {
  const [page, setPage] = useState(1)
  const [state, reload] = useRemote(`ejecuciones/${execution}/accesos`, { page, page_size: PAGE_SIZE })
  return <Loading state={state} reload={reload}>{(data) => <>
    {data.results.length ? <div className="crawl-table-wrap"><table className="crawl-table">
      <caption className="visually-hidden">Accesos de la ejecución {execution}</caption>
      <thead><tr><th scope="col">Tipo</th><th scope="col">HTTP</th><th scope="col">Estado del documento</th><th scope="col">URL</th><th scope="col">Hora</th><th scope="col">Publicación</th></tr></thead>
      <tbody>{data.results.map((a) => <tr key={a.id}>
        <td data-label="Tipo">{label(a.rol)}</td>
        <td data-label="HTTP">{a.http_status || 'Sin respuesta'}</td>
        <td data-label="Estado del documento">{label(a.resultado)}</td>
        <td data-label="URL" className="crawl-url">{safeUrl(a.url_original)
          ? <a href={a.url_original} title={a.url_original} target="_blank" rel="noopener noreferrer">{a.url_original}</a>
          : <span title={a.url_original}>{a.url_original}</span>}</td>
        <td data-label="Hora"><time dateTime={a.inicio_peticion_en || undefined}>{hour(a.inicio_peticion_en)}</time></td>
        <td data-label="Publicación">{a.publicacion_id ? <Link to={`/gestion/rastreo/publicaciones/${a.publicacion_id}`}>#{a.publicacion_id}</Link> : '—'}</td>
      </tr>)}</tbody>
    </table></div> : <p>No hay accesos registrados en esta ejecución.</p>}
    <Pager data={data} page={page} setPage={setPage} label="Accesos" />
  </>}</Loading>
}

function IncidentGroup({ execution, group, label }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return <li className="crawl-group">
    <button type="button" className="crawl-group-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
      <span className={`crawl-gravity crawl-gravity-${group.gravedad}`}>{group.gravedad === 'error' ? 'Error' : 'Aviso'}</span>
      <span className="crawl-group-name">{label(group.codigo)}</span>
      <span className="crawl-group-count">×{group.total}</span>
    </button>
    {open && <div id={id} className="crawl-group-detail"><IncidentRows execution={execution} group={group} /></div>}
  </li>
}

function IncidentRows({ execution, group }) {
  const [page, setPage] = useState(1)
  const [state, reload] = useRemote(`ejecuciones/${execution}/incidencias`, { codigo: group.codigo, gravedad: group.gravedad, page, page_size: PAGE_SIZE })
  return <Loading state={state} reload={reload}>{(data) => <>
    <ul className="crawl-incidents">{data.results.map((i) => <li key={i.id}>
      <time dateTime={i.detectada_en || undefined}>{hour(i.detectada_en)}</time>
      {i.publicacion_id ? <Link to={`/gestion/rastreo/publicaciones/${i.publicacion_id}`}>Publicación #{i.publicacion_id}</Link> : <span>Sin publicación asociada</span>}
      {/* Motivo de las incidencias editoriales (la API solo lo envía para ellas); texto plano, sin enlaces. */}
      {typeof i.detalle === 'string' && i.detalle.trim() && <p className="crawl-incident-reason">{i.detalle}</p>}
    </li>)}</ul>
    <Pager data={data} page={page} setPage={setPage} label={`${group.codigo} (${group.gravedad})`} />
  </>}</Loading>
}

function Incidents({ execution, label }) {
  const [gravity, setGravity] = useState('')
  const [state, reload] = useRemote(`ejecuciones/${execution}/incidencias`, { page: 1, page_size: 1 })
  const filterId = useId()
  return <Loading state={state} reload={reload}>{(data) => {
    const summary = data.resumen || []
    const totals = { '': data.count, error: 0, aviso: 0 }
    summary.forEach((g) => { totals[g.gravedad] = (totals[g.gravedad] || 0) + g.total })
    const groups = summary.filter((g) => !gravity || g.gravedad === gravity)
    return <>
      <div className="crawl-gravity-filter"><label htmlFor={filterId}>Gravedad</label>
        <select id={filterId} value={gravity} onChange={(event) => setGravity(event.target.value)}>
          {gravityOptions.map(([value, name]) => <option key={value} value={value}>{name} ({totals[value] || 0})</option>)}
        </select></div>
      {groups.length ? <ul className="crawl-groups" aria-label="Incidencias agrupadas por tipo">{groups.map((g) =>
        <IncidentGroup key={`${g.codigo}:${g.gravedad}`} execution={execution} group={g} label={label} />)}</ul>
        : <p>No hay incidencias{gravity ? ` de gravedad ${gravity}` : ''} en esta ejecución.</p>}
    </>
  }}</Loading>
}

export default function ExecutionTabs({ execution, item, label }) {
  const [tab, setTab] = useState('accesos')
  const base = useId()
  const incidents = item && item.incidencias_error != null ? item.incidencias_error + item.incidencias_aviso : null
  const tabs = [['accesos', 'Accesos', item?.accesos], ['incidencias', 'Incidencias', incidents]]
  const move = (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'Home' ? 'accesos' : event.key === 'End' ? 'incidencias' : tab === 'accesos' ? 'incidencias' : 'accesos'
    setTab(next)
    document.getElementById(`${base}-${next}`)?.focus()
  }
  return <section className="profile-card crawl-execution-tabs">
    <div role="tablist" aria-label="Detalle de la ejecución" className="heading-actions crawl-tabs" onKeyDown={move}>
      {tabs.map(([key, name, count]) => <button key={key} type="button" role="tab" id={`${base}-${key}`} aria-selected={tab === key}
        aria-controls={`${base}-${key}-panel`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)}>
        {name}{count != null && <span className="crawl-tab-count"> ({count})</span>}</button>)}
    </div>
    <div role="tabpanel" id={`${base}-${tab}-panel`} aria-labelledby={`${base}-${tab}`}>
      {tab === 'accesos' ? <Accesses key={`a:${execution}`} execution={execution} label={label} />
        : <Incidents key={`i:${execution}`} execution={execution} label={label} />}
    </div>
  </section>
}
