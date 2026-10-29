import Icon from './Icon'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import ProfileLayout from './ProfileLayout'

export default function OffersLayout({ children }) {
  const { user } = useAuth()
  if (user) return <ProfileLayout>{children}</ProfileLayout>
  return <div><header className="public-topbar"><Link className="brand" to="/becas">BecaNexo</Link><nav className="heading-actions" aria-label="Acceso a la cuenta"><Link to="/login"><Icon name="login" /><span>Iniciar sesión</span></Link><Link className="secondary-link" to="/registro"><Icon name="register" /><span>Crear cuenta</span></Link></nav></header>
    <main id="contenido" className="catalog-main">{children}</main><footer className="home-footer">BecaNexo · Ofertas de entidades ecuatorianas</footer></div>
}
