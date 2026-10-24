export default function Button({ children, busy = false, className = '', ...props }) {
  return <button className={`button ${className}`} aria-busy={busy} disabled={busy || props.disabled} {...props}>{children}</button>
}
