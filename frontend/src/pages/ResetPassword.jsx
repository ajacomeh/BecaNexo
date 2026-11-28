import Icon from '../components/Icon'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import AuthLayout from '../components/AuthLayout'
import Button from '../components/Button'
import Field from '../components/Field'
import Message from '../components/Message'

// El enlace del correo trae uid y token en el fragmento (#): el navegador no los envía al servidor.
function readLink(hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''))
  const uid = params.get('uid')
  const token = params.get('token')
  return uid && token ? { uid, token } : null
}

export default function ResetPassword() {
  const navigate = useNavigate()
  const location = useLocation()
  const [link] = useState(() => readLink(location.hash))
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [fields, setFields] = useState({})
  const [expired, setExpired] = useState(!link)

  // Quita uid y token de la barra de direcciones una vez leídos.
  useEffect(() => { if (location.hash) navigate(location.pathname, { replace: true }) }, [location.hash, location.pathname, navigate])

  async function submit(event) {
    event.preventDefault()
    if (pending.current) return
    const data = Object.fromEntries(new FormData(event.currentTarget))
    const invalid = {}
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
      await authApi.resetPassword({ ...link, ...data })
      navigate('/login', { replace: true, state: { passwordReset: true } })
    } catch (failure) {
      if (failure.fields?.codigo === 'enlace_invalido') setExpired(true)
      else {
        setError(failure.fields?.password || failure.fields?.password_confirm ? null : failure.message)
        setFields(failure.fields || {})
      }
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  if (expired) return <AuthLayout>
    <h1>Enlace no válido</h1>
    <Message>El enlace no es válido o ya venció. Solicita uno nuevo.</Message>
    <div><Link className="button" to="/recuperar-contrasena"><Icon name="mail" /><span>Solicitar un enlace nuevo</span></Link></div>
    <Link className="secondary-link" to="/login"><Icon name="login" /><span>Volver a iniciar sesión</span></Link>
  </AuthLayout>

  return <AuthLayout>
    <h1>Crea una contraseña nueva</h1>
    <p className="subtitle">Después podrás iniciar sesión con ella.</p>
    <Message>{error}</Message>
    <form noValidate onSubmit={submit} aria-label="Restablecer contraseña" aria-busy={busy}>
      <Field label="Contraseña nueva" name="password" type="password" autoComplete="new-password" required error={fields.password} disabled={busy}
        hint="Usa al menos 8 caracteres. Evita contraseñas comunes, solo numéricas o similares a tus datos." />
      <Field label="Confirmar contraseña" name="password_confirm" type="password" autoComplete="new-password" required error={fields.password_confirm} disabled={busy} />
      <Button icon="success" type="submit" busy={busy}>{busy ? 'Guardando…' : 'Guardar contraseña'}</Button>
    </form>
    <Link className="secondary-link" to="/login"><Icon name="login" /><span>Volver a iniciar sesión</span></Link>
  </AuthLayout>
}
