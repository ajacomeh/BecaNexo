import { useState } from 'react'
import { profileApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import ProfileForm from './ProfileForm'
import ConfirmDelete from './ConfirmDelete'

export default function ProfileRecords({ resource, title, singular, fields, initial, describe }) {
  const [records, setRecords] = useState(initial)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [notice, setNotice] = useState(null)
  async function save(data) {
    const result = await profileApi.write(`${resource}${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', data)
    setRecords((current) => editing.id ? current.map((row) => row.id === result.id ? result : row) : [...current, result])
    setEditing(null); setNotice('Cambios guardados.')
  }
  return <section className="profile-card" aria-label={title}>
    <h2>{title}</h2>
    {records.length === 0 && <p className="empty-note">Aún no has registrado {title.toLowerCase()}. La ausencia de datos no significa que no cumplas un requisito.</p>}
    <ul className="record-list">{records.map((row) => <li key={row.id}>
      <span>{describe(row)}</span><div className="record-actions">
        <button className="text-button" onClick={() => { setEditing(row); setNotice(null) }} disabled={editing !== null} aria-label={`Editar ${singular}: ${describe(row)}`}>Editar</button>
        <button className="text-button danger-text" onClick={() => setDeleting(row)} disabled={editing !== null} aria-label={`Eliminar ${singular}: ${describe(row)}`}>Eliminar</button>
      </div>
    </li>)}</ul>
    <Message kind="success">{notice}</Message>
    {editing ? <div className="record-editor"><h3>{editing.id ? 'Editar' : 'Añadir'} {singular}</h3>
      <ProfileForm key={editing.id || 'new'} fields={fields} initial={editing} onSubmit={save} onCancel={() => setEditing(null)} label={`Guardar ${singular}`} />
    </div> : <Button type="button" className="button-light" onClick={() => { setEditing({}); setNotice(null) }}>Añadir {singular}</Button>}
    {deleting && <ConfirmDelete title={singular} onCancel={() => setDeleting(null)} onConfirm={async () => {
      await profileApi.write(`${resource}/${deleting.id}`, 'DELETE')
      setRecords((current) => current.filter((row) => row.id !== deleting.id))
      setDeleting(null); setNotice('Registro eliminado.')
    }} />}
  </section>
}
