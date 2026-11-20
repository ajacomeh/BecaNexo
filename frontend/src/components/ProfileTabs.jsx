import { Link, NavLink } from 'react-router-dom'

// Control segmentado entre las dos pantallas del perfil. NavLink marca aria-current="page" en la activa.
export function ProfileTabs() {
  return <nav className="profile-tabs" aria-label="Secciones del perfil">
    <NavLink to="/perfil" end>Datos y formación</NavLink>
    <NavLink to="/preferencias" end>Idiomas y preferencias</NavLink>
  </nav>
}

// Franja discreta con lo que falta para comparar mejor; cada pendiente enlaza a su sección. Sin faltantes no se muestra.
export function ProfileMissing({ items }) {
  if (!items.length) return null
  return <aside className="profile-missing" aria-label="Datos pendientes del perfil">
    <p>Te faltan: {items.map((item, index) => <span key={item.label}>
      <Link to={item.to}>{item.label}</Link>{index < items.length - 1 ? ', ' : '.'}
    </span>)}</p>
  </aside>
}
