import Icon from '../components/Icon'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { authApi } from '../api/client'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/Button'
import Field from '../components/Field'
import Message from '../components/Message'

// La respuesta es siempre la misma: no revela si el correo tiene una cuenta.
export const GENERIC_SENT = 'Si el correo corresponde a una cuenta, te enviamos un enlace para restablecer la contraseña.'

export default function ForgotPassword() {
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [fieldError, setFieldError] = useState(null)
  const [sent, setSent] = useState(null)

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const email = new FormData(event.currentTarget).get('email').trim()
    const invalid = !email ? 'Ingresa tu correo electrónico.' : !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? 'Ingresa un correo válido.' : null
    setFieldError(invalid)
    setError(null)
    if (invalid) {
      event.currentTarget.elements.email.focus()
      return
    }
    pending.current = true
    setBusy(true)
    try {
      const result = await authApi.requestPasswordReset(email)
      setSent(typeof result.detail === 'string' ? result.detail : GENERIC_SENT)
    } catch (failure) {
      setError(failure.message)
      setFieldError(failure.fields?.email || null)
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return <AuthLayout>
    <h1>Recupera tu contraseña</h1>
    <p className="subtitle">Te enviaremos un enlace al correo de tu cuenta.</p>
    <Message>{error}</Message>
    {sent ? <Message kind="success">{sent} Revisa también la carpeta de correo no deseado.</Message> :
      <form noValidate onSubmit={submit} aria-label="Recuperar contraseña" aria-busy={busy}>
        <Field label="Correo electrónico" name="email" type="email" autoComplete="username" placeholder="tu@correo.com" required maxLength={254} error={fieldError} disabled={busy} />
        <Button icon="mail" type="submit" busy={busy}>{busy ? 'Enviando…' : 'Enviar enlace'}</Button>
      </form>}
    <Link className="secondary-link" to="/login"><Icon name="login" /><span>Volver a iniciar sesión</span></Link>
  </AuthLayout>
}
