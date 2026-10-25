import { useRef, useState } from 'react'
import { useAuth } from '../auth/context'
import Button from '../components/Button'
import Message from '../components/Message'
import { Link } from 'react-router-dom'

export default function Home() {
  const { user, logout } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const pending = useRef(false)
  async function leave() {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError(null)
    try { await logout() } catch (failure) { setError(failure.message) }
    finally { pending.current = false; setBusy(false) }
  }
  return <div className="home-layout">
    <header className="home-header">
      <span className="brand">BecaNexo</span>
      <Button className="button-outline" busy={busy} onClick={leave}>{busy ? 'Cerrando sesión…' : 'Cerrar sesión'}</Button>
    </header>
    <main id="contenido" className="home-main">
      <span className="eyebrow">PANTALLA INICIAL DEL AVANCE</span>
      <h1>Hola, {user.nombre}</h1>
      <p className="subtitle">Te damos la bienvenida a tu espacio en BecaNexo.</p>
      <Message>{error}</Message>
      <section className="account-card" aria-labelledby="cuenta-title">
        <h2 id="cuenta-title">Tu cuenta</h2>
        <dl className="grid gap-6 sm:grid-cols-2">
          <div><dt>Nombre</dt><dd>{user.nombre}</dd></div>
          <div><dt>Rol</dt><dd className="capitalize">{user.rol}</dd></div>
        </dl>
      </section>
      {user.rol === 'postulante' && <nav className="form-actions" aria-label="Tu perfil"><Link className="secondary-link" to="/perfil">Completar mi perfil</Link><Link className="secondary-link" to="/preferencias">Idiomas y preferencias</Link></nav>}
      <nav className="form-actions" aria-label="Convocatorias"><Link className="secondary-link" to="/becas">Explorar becas</Link>{user.rol === 'administrador' && <Link className="secondary-link" to="/gestion/convocatorias">Gestionar convocatorias</Link>}</nav>
      {user.rol === 'postulante' && <Link className="secondary-link" to="/favoritos">Mis favoritas</Link>}
      <p className="scope-note">Consulta ofertas publicadas y sus condiciones. La postulación y la verificación documental se realizan ante la entidad oferente.</p>
    </main>
    <footer className="home-footer">BecaNexo · Proyecto de tesis · Avance inicial</footer>
  </div>
}
