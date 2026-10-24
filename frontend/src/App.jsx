import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/context'
import AuthLayout from './components/AuthLayout'
import Button from './components/Button'
import Message from './components/Message'
import Login from './pages/Login'
import Register from './pages/Register'
import Home from './pages/Home'

export default function App() {
  const { status, error, retry } = useAuth()
  if (status === 'loading') return <AuthLayout><p role="status">Comprobando tu sesión…</p></AuthLayout>
  if (status === 'error') return <AuthLayout>
    <h1>No pudimos comprobar tu sesión</h1>
    <Message>{error}</Message>
    <Button onClick={retry}>Reintentar conexión</Button>
  </AuthLayout>
  const authenticated = status === 'authenticated'
  return <>
    <a className="skip-link" href="#contenido">Saltar al contenido</a>
    <Routes>
      <Route path="/login" element={authenticated ? <Navigate to="/inicio" replace /> : <Login />} />
      <Route path="/registro" element={authenticated ? <Navigate to="/inicio" replace /> : <Register />} />
      <Route path="/inicio" element={authenticated ? <Home /> : <Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to={authenticated ? '/inicio' : '/login'} replace />} />
    </Routes>
  </>
}
