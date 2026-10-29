import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import Icon from '../components/Icon'
import ProfileLayout from '../components/ProfileLayout'
import './Home.css'

const modules = {
  postulante: [
    { route: '/becas', icon: 'explore', title: 'Explorar becas', description: 'Consulta oportunidades y sus requisitos.' },
    { route: '/perfil', icon: 'profile', title: 'Mi perfil', description: 'Revisa y actualiza tu información declarada.' },
    { route: '/preferencias', icon: 'preferences', title: 'Idiomas y preferencias', description: 'Gestiona tus idiomas y preferencias de estudio.' },
    { route: '/favoritos', icon: 'favorite', title: 'Mis favoritas', description: 'Consulta las becas que has guardado.' },
  ],
  administrador: [
    { route: '/gestion/convocatorias', icon: 'offers', title: 'Convocatorias', description: 'Gestiona las ofertas del catálogo.' },
    { route: '/gestion/instituciones', icon: 'institutions', title: 'Entidades oferentes', description: 'Consulta y gestiona entidades oferentes.' },
    { route: '/gestion/rastreo', icon: 'crawling', title: 'Rastreo', description: 'Consulta publicaciones detectadas, documentos y ejecuciones.' },
  ],
}

export default function Home() {
  const { user } = useAuth()
  return <ProfileLayout>
    <div className="home-dashboard">
      <p className="eyebrow">Tu espacio en BecaNexo</p>
      <h1>Hola, {user.nombre}</h1>
      <p className="subtitle">Te damos la bienvenida a tu espacio en BecaNexo.</p>
      <nav className="home-module-grid" aria-label="Accesos de Inicio">
        {modules[user.rol].map(({ route, icon, title, description }, index) =>
          <Link key={route} className="home-module-card" to={route} aria-labelledby={`home-module-${index}`} aria-describedby={`home-description-${index}`}>
            <Icon name={icon} />
            <div><h2 id={`home-module-${index}`}>{title}</h2><p id={`home-description-${index}`}>{description}</p></div>
          </Link>
        )}
      </nav>
      <p className="scope-note">Consulta ofertas publicadas y sus condiciones. La postulación y la verificación documental se realizan ante la entidad oferente.</p>
    </div>
  </ProfileLayout>
}
