import Icon from './Icon'

export default function Message({ children, kind = 'error' }) {
  if (!children) return null
  return <div className={`message message-${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Icon name={kind === 'error' ? 'warning' : kind === 'success' ? 'success' : 'info'} /><div>{children}</div></div>
}
