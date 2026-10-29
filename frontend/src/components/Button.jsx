import Icon from './Icon'

export default function Button({ children, icon, busy = false, disabled = false, className = '', ...props }) {
  return <button {...props} className={`button ${className}`} aria-busy={busy} disabled={busy || disabled}>{(busy || icon) && <Icon name={busy ? 'loading' : icon} />}<span>{children}</span></button>
}
