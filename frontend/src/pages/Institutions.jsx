import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Message from '../components/Message'
import Button from '../components/Button'
import InstitutionDialog from '../components/InstitutionDialog'
import './Institutions.css'

const PAGE_SIZE = 25
const FETCH_SIZE = 50 // máximo de la API; se recorren las páginas para filtrar por sector en el cliente
const MAX_PAGES = 40
const DEMO_PREFIX = /^DEMOSTRACIÓN\s*·\s*/i
const sectors = [['', 'Todos'], ['publico', 'Pública'], ['privado', 'Privada']]
const sectorLabel = (value) => sectors.find(([key]) => key === value)?.[1] || value

// Solo presentación: el nombre registrado no cambia.
function presentName(name = '') {
  const demo = DEMO_PREFIX.test(name)
  return { demo, title: demo ? name.replace(DEMO_PREFIX, '') : name }
}

async function loadAll(query) {
  const rows = []
  for (let page = 1; page <= MAX_PAGES; page++) {
    const data = await offersApi.get('gestion/instituciones', { page, page_size: FETCH_SIZE, q: query })
    rows.push(...data.results)
    if (page * data.page_size >= data.count || !data.results.length) break
  }
  return rows
}

export default function Institutions() {
  const [loaded, setLoaded] = useState({ key: null, rows: null, error: '' })
  const [catalogs, setCatalogs] = useState(null)
  const [editing, setEditing] = useState(null)
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [sector, setSector] = useState('')
  const [filters, setFilters] = useState({ query: '', sector: '' })
  const [revision, setRevision] = useState(0)
  // La consulta vigente se identifica por su clave: mientras no coincide con la cargada, se muestra «Cargando…».
  const key = `${filters.query}|${revision}`
  useEffect(() => {
    let live = true
    Promise.all([loadAll(filters.query), offersApi.get('becas/catalogos')])
      .then(([list, c]) => { if (live) { setLoaded({ key, rows: list, error: '' }); setCatalogs(c) } })
      .catch((e) => { if (live) setLoaded({ key, rows: null, error: e.message }) })
    return () => { live = false }
  }, [key, filters.query])
  const rows = loaded.key === key ? loaded.rows : null
  const error = loaded.key === key ? loaded.error : ''
  useEffect(() => {
    if (!notice) return undefined
    const timer = setTimeout(() => setNotice(''), 5000)
    return () => clearTimeout(timer)
  }, [notice])

  const filtered = (rows || []).filter((r) => !filters.sector || r.sector === filters.sector)
  const count = filtered.length
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  const current = Math.min(page, totalPages)
  const visible = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE)
  const active = filters.query || filters.sector
  const apply = (event) => { event.preventDefault(); setFilters({ query: search.trim(), sector }); setPage(1) }
  const clear = () => { setSearch(''); setSector(''); setFilters({ query: '', sector: '' }); setPage(1) }
  const save = async (values) => {
    await offersApi.write(`gestion/instituciones${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', values)
    setEditing(null); setNotice('Entidad guardada.'); setRevision((value) => value + 1)
  }

  return <OffersLayout><div className="institutions-page">
    <div className="page-heading"><div><p className="eyebrow">ADMINISTRACIÓN</p><h1>Entidades oferentes</h1><p>Solo entidades ecuatorianas. El país de estudio se define por separado en cada opción.</p></div>
      <div className="heading-actions"><Button icon="add" disabled={!catalogs} onClick={() => setEditing({})}>Añadir entidad oferente</Button></div></div>
    {notice && <div className="institution-notice"><Message kind="success">{notice}</Message></div>}
    <form className="profile-card institution-search" role="search" aria-label="Filtrar entidades oferentes" onSubmit={apply}>
      <label htmlFor="institution-query">Buscar entidad<input id="institution-query" type="search" maxLength={200} value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label htmlFor="institution-sector">Sector<select id="institution-sector" value={sector} onChange={(event) => setSector(event.target.value)}>
        {sectors.map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
      <div className="institution-search-actions"><Button icon="search" type="submit">Aplicar</Button>
        <Button icon="clear" className="button-light" type="button" disabled={!active && !search && !sector} onClick={clear}>Limpiar filtros</Button></div>
    </form>
    <section className="profile-card" aria-labelledby="institution-list-title">
      <div className="list-heading institution-list-heading"><h2 id="institution-list-title">Oferentes registrados</h2>
        {rows && <p role="status" className="institution-count">{count} {count === 1 ? 'entidad' : 'entidades'}</p>}</div>
      {error ? <><Message>{error}</Message><Button icon="refresh" onClick={() => setRevision(revision + 1)}>Reintentar</Button></>
        : !rows ? <p role="status"><Icon name="loading" />Cargando entidades oferentes…</p>
        : visible.length ? <ul className="institution-list">{visible.map((r) => {
          const { demo, title } = presentName(r.nombre)
          return <li key={r.id} className="institution-row">
            <span className="institution-initial" aria-hidden="true">{(title.trim()[0] || '?').toUpperCase()}</span>
            <div className="institution-identity"><strong title={r.nombre}>{title}</strong>
              <div className="institution-tags"><span className={`status-pill institution-sector institution-sector-${r.sector}`}>{sectorLabel(r.sector)}</span>
                {demo && <span className="status-pill institution-demo">Demostración</span>}</div></div>
            <button type="button" className="text-button" disabled={!catalogs} aria-label={`Editar ${title}`} onClick={() => setEditing(r)}><Icon name="edit" /><span>Editar</span></button>
          </li>
        })}</ul>
        : <p className="empty-note">{active ? 'No hay entidades con esos filtros.' : 'No hay entidades oferentes registradas.'}</p>}
      {rows && count > PAGE_SIZE && <nav className="pagination" aria-label="Paginación de oferentes">
        <Button icon="previous" disabled={current <= 1} onClick={() => setPage(current - 1)}>Anterior</Button>
        <span aria-live="polite">{(current - 1) * PAGE_SIZE + 1}–{Math.min(current * PAGE_SIZE, count)} de {count}</span>
        <Button icon="next" disabled={current >= totalPages} onClick={() => setPage(current + 1)}>Siguiente</Button></nav>}
    </section>
    {editing && catalogs && <InstitutionDialog institution={editing} catalogs={catalogs} onClose={() => setEditing(null)} onSaved={save} />}
  </div></OffersLayout>
}
