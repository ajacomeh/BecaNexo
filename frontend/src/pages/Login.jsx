import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/context'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/Button'
import Field from '../components/Field'
import Message from '../components/Message'
import { loginReturnPath } from '../auth/returnPath'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [fields, setFields] = useState({})

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const data = Object.fromEntries(new FormData(event.currentTarget))
    const invalid = {}
    if (!data.email.trim()) invalid.email = 'Ingresa tu correo electrónico.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) invalid.email = 'Ingresa un correo válido.'
    if (!data.password) invalid.password = 'Ingresa tu contraseña.'
    setFields(invalid)
    setError(null)
    if (Object.keys(invalid).length) {
      event.currentTarget.elements[Object.keys(invalid)[0]].focus()
      return
    }
    pending.current = true
    setBusy(true)
    try {
      await login(data)
      navigate(loginReturnPath(location.search), { replace: true })
    } catch (failure) {
      setError(failure.message)
      setFields(failure.fields || {})
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return <AuthLayout>
    <h1>Inicia sesión</h1>
    <p className="subtitle">Usa tu correo para acceder a tu espacio.</p>
    {location.state?.registered && <Message kind="success">Tu cuenta fue creada. Ya puedes iniciar sesión.</Message>}
    <Message>{error}</Message>
    <form noValidate onSubmit={submit} aria-label="Iniciar sesión" aria-busy={busy}>
      <Field label="Correo electrónico" name="email" type="email" autoComplete="username" placeholder="tu@correo.com" required maxLength={254} error={fields.email} disabled={busy} />
      <Field label="Contraseña" name="password" type="password" autoComplete="current-password" required error={fields.password} disabled={busy} />
      <Button type="submit" busy={busy}>{busy ? 'Iniciando sesión…' : 'Iniciar sesión'}</Button>
    </form>
    <Link className="secondary-link" to="/registro">Crear una cuenta</Link>
  </AuthLayout>
}
