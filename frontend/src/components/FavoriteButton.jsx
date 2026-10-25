import { useRef, useState } from 'react'
import { useAuth } from '../auth/context'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

export default function FavoriteButton({ offerId, initialId = null, onRemoved }) {
  const { user } = useAuth()
  const [favoriteId, setFavoriteId] = useState(initialId)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  if (user?.rol !== 'postulante') return null
  async function toggle() {
    if (pending.current) return
    pending.current = true; setBusy(true); setError('')
    try {
      if (favoriteId) {
        await offersApi.write(`favoritos/${favoriteId}`, 'DELETE')
        setFavoriteId(null); onRemoved?.()
      } else {
        const result = await offersApi.write('favoritos', 'POST', { convocatoria: offerId })
        setFavoriteId(result.id)
      }
    } catch (e) { setError(e.status === 404 ? 'La oportunidad o el favorito ya no está disponible. Actualiza la página.' : e.message) }
    finally { pending.current = false; setBusy(false) }
  }
  return <div className="favorite-control"><Button className="button-light" busy={busy} aria-pressed={Boolean(favoriteId)} onClick={toggle}>
    {busy ? 'Guardando cambio…' : favoriteId ? 'Quitar de favoritos' : 'Guardar en favoritos'}</Button><Message>{error}</Message></div>
}
