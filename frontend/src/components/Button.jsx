export default function Button({ children, busy = false, disabled = false, className = '', ...props }) {
  return <button {...props} className={`button ${className}`} aria-busy={busy} disabled={busy || disabled}>{children}</button>
}
