import Icon from './Icon'
import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/context'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import EditName from './EditName'

const ROLE_LABELS = { administrador: 'Administrador', postulante: 'Postulante' }

export default function ProfileLayout({ children }) {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const [unread, setUnread] = useState(0)
  useEffect(() => {
    if (user.rol !== 'postulante') return undefined
    let live = true
    let requestId = 0
    const refresh = () => {
      const id = ++requestId
      offersApi.get('notificaciones', { page_size: 1 })
        .then((data) => { if (live && id === requestId) setUnread(data.no_leidas || 0) })
        .catch(() => { if (live && id === requestId) setUnread(0) })
    }
    refresh()
    window.addEventListener('becanexo:notificaciones', refresh)
    return () => { live = false; window.removeEventListener('becanexo:notificaciones', refresh) }
  }, [user.rol])
  async function leave() {
    if (busy) return
    setBusy(true)
    try { await logout() } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  return <div className="profile-layout">
    <aside className="profile-sidebar">
      <span className="brand">BecaNexo</span><p className="sidebar-tag">TU PRÓXIMA OPORTUNIDAD</p>
      <nav aria-label="Navegación principal">
        <NavLink to="/inicio"><Icon name="home" /><span>Inicio</span></NavLink>
        {user.rol === 'postulante' && <><NavLink to="/perfil"><Icon name="profile" /><span>Mi perfil académico</span></NavLink><NavLink to="/preferencias"><Icon name="preferences" /><span>Idiomas y preferencias</span></NavLink></>}
        <NavLink to="/becas"><Icon name="explore" /><span>Explorar becas</span></NavLink>
        {user.rol === 'postulante' && <NavLink to="/favoritos"><Icon name="favorite" /><span>Mis favoritas</span></NavLink>}
        {user.rol === 'postulante' && <NavLink to="/notificaciones" aria-label={unread ? `Notificaciones, ${unread} sin leer` : undefined}><Icon name="notifications" /><span>Notificaciones</span>{unread > 0 && <span className="notification-nav-count" aria-hidden="true">{unread}</span>}</NavLink>}
        {user.rol === 'administrador' && <><NavLink to="/gestion/convocatorias"><Icon name="offers" /><span>Convocatorias</span></NavLink><NavLink to="/gestion/instituciones"><Icon name="institutions" /><span>Entidades oferentes</span></NavLink><NavLink to="/gestion/rastreo"><Icon name="crawling" /><span>Rastreo</span></NavLink></>}
      </nav>
      {/* Bloque de usuario: nombre (con edición para el administrador) y el rol como etiqueta; sin avatar. */}
      <div className="sidebar-account"><div className="sidebar-user"><div className="sidebar-name"><span>{user.nombre}</span>{user.rol === 'administrador' && <button type="button" className="edit-name-link" aria-label="Editar nombre" title="Editar nombre" disabled={busy} onClick={() => { setSaved(false); setEditing(true) }}><Icon name="edit" /></button>}</div>
        <span className="sidebar-role">{ROLE_LABELS[user.rol] || user.rol}</span></div>
        {saved && <span role="status">Nombre actualizado.</span>}
        <Button icon="logout" className="button-outline" busy={busy} onClick={leave}>{busy ? 'Cerrando sesión…' : 'Cerrar sesión'}</Button>
        <Message>{error}</Message>
      </div>
    </aside>
    {editing && <EditName onClose={() => setEditing(false)} onSaved={() => { setEditing(false); setSaved(true) }} />}
    <div className="profile-body"><header className="profile-topbar">{user.rol === 'administrador' ? 'Espacio de administración' : 'Tu espacio de oportunidades'} <span>BecaNexo</span></header>
      <main id="contenido" className="profile-main">{children}</main>
      <footer className="home-footer">BecaNexo · Proyecto de tesis</footer>
    </div>
  </div>
}
