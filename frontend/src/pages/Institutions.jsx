import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import OfferForm from '../components/OfferForm'
import Message from '../components/Message'
import Button from '../components/Button'
import { institutionFields } from './offerFields'
import './Institutions.css'

export default function Institutions() {
  const [data, setData] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get('gestion/instituciones', { page, q: query }), offersApi.get('becas/catalogos')]).then(([d, c]) => { if (live) { setData(d); setCatalogs(c); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [page, query, revision])
  const totalPages = data && data.page_size > 0 ? Math.ceil(data.count / data.page_size) : 0
  const clearSearch = () => { setSearch(''); setQuery(''); setPage(1) }

  return <OffersLayout><div className="institutions-page"><h1>Entidades oferentes</h1><p>Solo entidades ecuatorianas. El país de estudio se define por separado en cada opción.</p><Message>{error}</Message>{error && <Button icon="refresh" onClick={() => setRevision(revision + 1)}>Reintentar</Button>}
    <form className="profile-card institution-search" role="search" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); setPage(1) }}><label htmlFor="institution-query">Buscar entidad<input id="institution-query" type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><div className="institution-search-actions"><Button icon="search" type="submit">Buscar</Button>{(query || search) && <Button icon="clear" className="button-light" type="button" onClick={clearSearch}>Limpiar</Button>}</div></form>
    {data && <section className="profile-card"><div className="list-heading institution-list-heading"><div><h2>Oferentes registrados</h2><p role="status" className="small-note">{data.count} {data.count === 1 ? 'entidad' : 'entidades'}</p></div><div className="heading-actions">{!editing && <Button icon="add" onClick={() => setEditing({})}>Añadir entidad oferente</Button>}</div></div>{data.results.length ? <ul className="record-list institution-list">{data.results.map((r) => <li key={r.id}><div className="institution-identity"><strong>{r.nombre}</strong><span className="status-pill">{r.sector === 'publico' ? 'Pública' : r.sector === 'privado' ? 'Privada' : r.sector}</span></div><button className="text-button" disabled={!!editing} onClick={() => setEditing(r)}><Icon name="edit" /><span>Editar</span></button></li>)}</ul> : <p className="empty-note">{query ? 'No encontramos entidades que coincidan con la búsqueda.' : 'No hay entidades oferentes registradas.'}</p>}
      {totalPages > 1 && <nav className="pagination" aria-label="Paginación de oferentes"><Button icon="previous" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page} de {totalPages}</span><Button icon="next" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</section>}
    {editing && catalogs && <section className="profile-card"><h2>{editing.id ? 'Editar oferente' : 'Nueva entidad oferente'}</h2><p className="profile-note">Editar un oferente devuelve sus convocatorias a revisión pendiente.</p><OfferForm key={editing.id || 'new'} fields={institutionFields(catalogs)} initial={{ pais: catalogs.paises.find((p) => p.codigo === 'EC')?.id, ...editing }} label="Guardar entidad" onCancel={() => setEditing(null)} onSubmit={async (values) => {
      await offersApi.write(`gestion/instituciones${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', values); setEditing(null); setRevision(revision + 1)
    }} /></section>}
  </div></OffersLayout>
}
