import { useEffect, useRef } from 'react'
import Icon from './Icon'
import OfferForm from './OfferForm'
import { institutionFields } from '../pages/offerFields'

const focusable = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Ventana emergente del formulario de entidad oferente: mismo patrón de <dialog> que «Editar nombre» y la confirmación de eliminación.
export default function InstitutionDialog({ institution, catalogs, onClose, onSaved }) {
  const dialog = useRef(null)
  const editing = Boolean(institution.id)
  const busy = useRef(false)
  useEffect(() => {
    const element = dialog.current
    const trigger = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden' // el fondo no se desplaza mientras el diálogo está abierto
    if (typeof element.showModal === 'function') element.showModal(); else element.setAttribute('open', '')
    element.querySelector('input, select, textarea')?.focus()
    return () => {
      document.body.style.overflow = overflow
      if (typeof element.close === 'function' && element.open) element.close()
      trigger?.focus?.()
    }
  }, [])
  const close = () => { if (!busy.current) onClose() }
  function keys(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(); return }
    if (event.key !== 'Tab') return
    const items = [...dialog.current.querySelectorAll(focusable)]
    if (!items.length) return
    const [first, last] = [items[0], items.at(-1)]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  const title = editing ? 'Editar entidad oferente' : 'Nueva entidad oferente'
  return <dialog ref={dialog} className="confirm-dialog institution-dialog" aria-modal="true" aria-labelledby="institution-dialog-title" aria-describedby="institution-dialog-note"
    onCancel={(event) => { event.preventDefault(); close() }} onKeyDown={keys}>
    <div className="institution-dialog-heading"><h2 id="institution-dialog-title">{title}</h2>
      <button type="button" className="institution-dialog-close" aria-label="Cerrar" onClick={close}><Icon name="clear" /></button></div>
    <p id="institution-dialog-note" className="profile-note">Editar un oferente devuelve sus convocatorias a revisión pendiente.</p>
    <OfferForm key={institution.id || 'new'} fields={institutionFields(catalogs)} initial={{ pais: catalogs.paises.find((p) => p.codigo === 'EC')?.id, ...institution }}
      label="Guardar entidad" onCancel={close} onSubmit={async (values) => {
        busy.current = true
        try { await onSaved(values) } finally { busy.current = false }
      }} />
  </dialog>
}
