export default function Message({ children, kind = 'error' }) {
  if (!children) return null
  return <div className={`message message-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}
