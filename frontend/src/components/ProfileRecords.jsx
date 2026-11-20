import Icon from './Icon'
import { useEffect, useState } from 'react'
import { profileApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import ProfileForm from './ProfileForm'
import ConfirmDelete from './ConfirmDelete'

// `describe` da el texto completo del registro (nombres accesibles y chips); `present` separa el texto principal
// de su estado o fechas para las filas. `variant="chips"` muestra cada registro como etiqueta con editar y quitar.
export default function ProfileRecords({ resource, anchorId, title, singular, fields, initial, describe, present, variant = 'rows', onCount }) {
  const [records, setRecords] = useState(initial)
  const [editing, setEditing] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [notice, setNotice] = useState(null)
  useEffect(() => { onCount?.(resource, records.length) }, [resource, records.length, onCount])
  async function save(data) {
    const result = await profileApi.write(`${resource}${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', data)
    setRecords((current) => editing.id ? current.map((row) => row.id === result.id ? result : row) : [...current, result])
    setEditing(null); setNotice('Cambios guardados.')
  }
  const edit = (row) => { setEditing(row); setNotice(null) }
  const actions = (row) => variant === 'chips' ? <>
    <button type="button" className="chip-action" onClick={() => edit(row)} disabled={editing !== null} title="Editar" aria-label={`Editar ${singular}: ${describe(row)}`}><Icon name="edit" /></button>
    <button type="button" className="chip-action chip-remove" onClick={() => setDeleting(row)} disabled={editing !== null} title="Eliminar" aria-label={`Eliminar ${singular}: ${describe(row)}`}><Icon name="delete" /></button>
  </> : <div className="record-actions">
    <button className="text-button" onClick={() => edit(row)} disabled={editing !== null} aria-label={`Editar ${singular}: ${describe(row)}`}><Icon name="edit" /><span>Editar</span></button>
    <button className="text-button danger-text" onClick={() => setDeleting(row)} disabled={editing !== null} aria-label={`Eliminar ${singular}: ${describe(row)}`}><Icon name="delete" /><span>Eliminar</span></button>
  </div>
  return <section className={`profile-card${editing ? ' profile-card-editing' : ''}`} aria-label={title}>
    <h2 id={anchorId} className={anchorId ? 'profile-anchor' : undefined} tabIndex={anchorId ? -1 : undefined}>{title}</h2>
    {records.length === 0 && <p className="empty-note">Aún no has registrado {title.toLowerCase()}. La ausencia de datos no significa que no cumplas un requisito.</p>}
    {variant === 'chips'
      ? records.length > 0 && <ul className="chip-list">{records.map((row) => <li key={row.id} className="profile-chip">
        <span className="chip-label">{describe(row)}</span>{actions(row)}
      </li>)}</ul>
      : <ul className="record-list record-rows">{records.map((row) => {
        const { title: main, tag, meta } = present ? present(row) : { title: describe(row) }
        return <li key={row.id}>
          <div className="record-main"><strong className="record-title">{main}</strong>
            {tag && <span className="record-tag">{tag}</span>}
            {meta && <span className="record-meta">{meta}</span>}</div>
          {actions(row)}
        </li>
      })}</ul>}
    <Message kind="success">{notice}</Message>
    {editing ? <div className="record-editor"><h3>{editing.id ? 'Editar' : 'Añadir'} {singular}</h3>
      <ProfileForm key={editing.id || 'new'} fields={fields} initial={editing} onSubmit={save} onCancel={() => setEditing(null)} label={`Guardar ${singular}`} />
    </div> : <Button icon="add" type="button" className="button-light" onClick={() => { setEditing({}); setNotice(null) }}>Añadir {singular}</Button>}
    {deleting && <ConfirmDelete title={singular} onCancel={() => setDeleting(null)} onConfirm={async () => {
      await profileApi.write(`${resource}/${deleting.id}`, 'DELETE')
      setRecords((current) => current.filter((row) => row.id !== deleting.id))
      setDeleting(null); setNotice('Registro eliminado.')
    }} />}
  </section>
}
