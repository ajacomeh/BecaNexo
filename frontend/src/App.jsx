import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { loginReturnPath } from './auth/returnPath'
import { useAuth } from './auth/context'
import AuthLayout from './components/AuthLayout'
import Button from './components/Button'
import Message from './components/Message'
import Login from './pages/Login'
import Register from './pages/Register'
import Home from './pages/Home'
import Profile from './pages/Profile'
import Offers from './pages/Offers'
import OfferDetail from './pages/OfferDetail'
import OfferEditor from './pages/OfferEditor'
import Institutions from './pages/Institutions'
import Favorites from './pages/Favorites'
import Welcome from './pages/Welcome'
import Crawling from './pages/Crawling'

export default function App() {
  const { status, error, retry, user } = useAuth()
  const location = useLocation()
  if (status === 'loading') return <AuthLayout><p role="status">Comprobando tu sesión…</p></AuthLayout>
  if (status === 'error') return <AuthLayout>
    <h1>No pudimos comprobar tu sesión</h1>
    <Message>{error}</Message>
    <Button onClick={retry}>Reintentar conexión</Button>
  </AuthLayout>
  const authenticated = status === 'authenticated'
  const admin = (element) => !authenticated ? <Navigate to="/login" replace /> : user.rol === 'administrador' ? element : <Navigate to="/inicio" replace />
  return <>
    <a className="skip-link" href="#contenido">Saltar al contenido</a>
    <Routes>
      <Route path="/" element={<Welcome />} />
      <Route path="/favoritos" element={!authenticated ? <Navigate to="/login" replace /> : user.rol === 'postulante' ? <Favorites /> : <Navigate to="/inicio" replace />} />
      <Route path="/becas" element={<Offers />} />
      <Route path="/becas/:id" element={<OfferDetail />} />
      <Route path="/gestion/convocatorias" element={admin(<Offers admin />)} />
      <Route path="/gestion/convocatorias/nueva" element={admin(<OfferEditor key="new" />)} />
      <Route path="/gestion/convocatorias/:id" element={admin(<OfferEditor key="edit" />)} />
      <Route path="/gestion/instituciones" element={admin(<Institutions />)} />
      <Route path="/gestion/rastreo/*" element={admin(<Crawling />)} />
      <Route path="/login" element={authenticated ? <Navigate to={loginReturnPath(location.search)} replace /> : <Login />} />
      <Route path="/registro" element={authenticated ? <Navigate to="/inicio" replace /> : <Register />} />
      <Route path="/inicio" element={authenticated ? <Home /> : <Navigate to="/login" replace />} />
      <Route path="/perfil" element={!authenticated ? <Navigate to="/login" replace /> : user.rol === 'postulante' ? <Profile key="perfil" /> : <Navigate to="/inicio" replace />} />
      <Route path="/preferencias" element={!authenticated ? <Navigate to="/login" replace /> : user.rol === 'postulante' ? <Profile key="preferencias" preferences /> : <Navigate to="/inicio" replace />} />
      <Route path="*" element={<Navigate to={authenticated ? '/inicio' : '/login'} replace />} />
    </Routes>
  </>
}
