import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import OfferForm from '../components/OfferForm'
import Message from '../components/Message'
import Button from '../components/Button'
import { institutionFields } from './offerFields'

export default function Institutions() {
  const [data, setData] = useState(null)
  const [catalogs, setCatalogs] = useState(null)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get('gestion/instituciones', { page, q: query }), offersApi.get('becas/catalogos')]).then(([d, c]) => { if (live) { setData(d); setCatalogs(c); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [page, query, revision])
  return <OffersLayout><h1>Entidades oferentes</h1><p>Solo entidades ecuatorianas. El país de estudio se define por separado en cada opción.</p><Message>{error}</Message>{error && <Button icon="refresh" onClick={() => setRevision(revision + 1)}>Reintentar</Button>}
    <section className="profile-card"><OfferForm fields={[{ name: 'q', label: 'Buscar entidad' }]} icon="search" label="Buscar" onSubmit={async ({ q }) => { setQuery(q || ''); setPage(1) }} /></section>
    {data && <section className="profile-card"><div className="list-heading"><h2>Oferentes registrados</h2><div className="heading-actions">{!editing && <Button icon="add" onClick={() => setEditing({})}>Añadir entidad oferente</Button>}</div></div><ul className="record-list">{data.results.map((r) => <li key={r.id}><span>{r.nombre} · {r.sector}</span><button className="text-button" disabled={!!editing} onClick={() => setEditing(r)}><Icon name="edit" /><span>Editar</span></button></li>)}</ul>
      <nav className="pagination" aria-label="Paginación de oferentes"><Button icon="previous" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page}</span><Button icon="next" disabled={page * data.page_size >= data.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav></section>}
    {editing && catalogs && <section className="profile-card"><h2>{editing.id ? 'Editar oferente' : 'Nueva entidad oferente'}</h2><p className="profile-note">Editar un oferente devuelve sus convocatorias a revisión pendiente.</p><OfferForm key={editing.id || 'new'} fields={institutionFields(catalogs)} initial={{ pais: catalogs.paises.find((p) => p.codigo === 'EC')?.id, ...editing }} label="Guardar entidad" onCancel={() => setEditing(null)} onSubmit={async (values) => {
      await offersApi.write(`gestion/instituciones${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', values); setEditing(null); setRevision(revision + 1)
    }} /></section>}
  </OffersLayout>
}
