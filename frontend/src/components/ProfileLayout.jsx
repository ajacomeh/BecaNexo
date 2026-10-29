import Icon from './Icon'
import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../auth/context'
import Button from './Button'
import Message from './Message'
import EditName from './EditName'

export default function ProfileLayout({ children }) {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
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
        {user.rol === 'administrador' && <><NavLink to="/gestion/convocatorias"><Icon name="offers" /><span>Convocatorias</span></NavLink><NavLink to="/gestion/instituciones"><Icon name="institutions" /><span>Entidades oferentes</span></NavLink><NavLink to="/gestion/rastreo"><Icon name="crawling" /><span>Rastreo</span></NavLink></>}
      </nav>
      <div className="sidebar-account"><div className="sidebar-name"><span>{user.nombre}</span><button type="button" className="edit-name-link" aria-label="Editar nombre" title="Editar nombre" disabled={busy} onClick={() => { setSaved(false); setEditing(true) }}><Icon name="edit" /></button></div><span className="capitalize">{user.rol}</span>
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
