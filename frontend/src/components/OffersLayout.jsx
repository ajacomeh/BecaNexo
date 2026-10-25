import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import ProfileLayout from './ProfileLayout'

export default function OffersLayout({ children }) {
  const { user } = useAuth()
  if (user) return <ProfileLayout>{children}</ProfileLayout>
  return <div><header className="public-topbar"><Link className="brand" to="/becas">BecaNexo</Link><nav><Link to="/login">Iniciar sesión</Link><Link className="secondary-link" to="/registro">Crear cuenta</Link></nav></header>
    <main id="contenido" className="catalog-main">{children}</main><footer className="home-footer">BecaNexo · Ofertas de entidades ecuatorianas</footer></div>
}
