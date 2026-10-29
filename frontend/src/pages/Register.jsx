import Icon from '../components/Icon'
import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/Button'
import Field from '../components/Field'
import Message from '../components/Message'

export default function Register() {
  const navigate = useNavigate()
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [fields, setFields] = useState({})

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const data = Object.fromEntries(new FormData(event.currentTarget))
    const invalid = {}
    if (!data.nombre.trim()) invalid.nombre = 'Ingresa tu nombre completo.'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) invalid.email = 'Ingresa un correo válido.'
    if (!data.password) invalid.password = 'Crea una contraseña.'
    if (!data.password_confirm) invalid.password_confirm = 'Confirma tu contraseña.'
    else if (data.password !== data.password_confirm) invalid.password_confirm = 'Las contraseñas no coinciden.'
    setFields(invalid)
    setError(null)
    if (Object.keys(invalid).length) {
      event.currentTarget.elements[Object.keys(invalid)[0]].focus()
      return
    }
    pending.current = true
    setBusy(true)
    try {
      await authApi.register(data)
      navigate('/login', { replace: true, state: { registered: true } })
    } catch (failure) {
      setError(failure.message)
      setFields(failure.fields || {})
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return <AuthLayout>
    <h1>Crea tu cuenta</h1>
    <p className="subtitle">Usa tu correo para acceder a tu espacio.</p>
    <Message>{error}</Message>
    <form noValidate onSubmit={submit} aria-label="Crear cuenta" aria-busy={busy}>
      <Field label="Nombre completo" name="nombre" autoComplete="name" required maxLength={180} error={fields.nombre} disabled={busy} />
      <Field label="Correo electrónico" name="email" type="email" autoComplete="email" placeholder="tu@correo.com" required maxLength={254} error={fields.email} disabled={busy} />
      <Field label="Contraseña" name="password" type="password" autoComplete="new-password" required error={fields.password} disabled={busy}
        hint="Usa al menos 8 caracteres. Evita contraseñas comunes, solo numéricas o similares a tus datos." />
      <Field label="Confirmar contraseña" name="password_confirm" type="password" autoComplete="new-password" required error={fields.password_confirm} disabled={busy} />
      <Button icon="register" type="submit" busy={busy}>{busy ? 'Creando tu cuenta…' : 'Crear mi cuenta'}</Button>
    </form>
    <Link className="secondary-link" to="/login"><Icon name="login" /><span>Ya tengo cuenta</span></Link>
  </AuthLayout>
}
