import { NavLink } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../auth/context'
import Button from './Button'
import Message from './Message'

export default function ProfileLayout({ children }) {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
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
        <NavLink to="/inicio">Inicio</NavLink>
        <NavLink to="/perfil">Mi perfil académico</NavLink>
        <NavLink to="/preferencias">Idiomas y preferencias</NavLink>
      </nav>
      <div className="sidebar-account"><span>{user.nombre}</span><span className="capitalize">{user.rol}</span>
        <Button className="button-outline" busy={busy} onClick={leave}>{busy ? 'Cerrando sesión…' : 'Cerrar sesión'}</Button>
        <Message>{error}</Message>
      </div>
    </aside>
    <div className="profile-body"><header className="profile-topbar">Tu espacio de oportunidades <span>Datos declarados</span></header>
      <main id="contenido" className="profile-main">{children}</main>
      <footer className="home-footer">BecaNexo · Proyecto de tesis · Perfil del postulante</footer>
    </div>
  </div>
}
