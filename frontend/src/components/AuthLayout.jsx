import { Link } from 'react-router-dom'

export default function AuthLayout({ children }) {
  return (
    <div className="auth-layout">
      <aside className="brand-panel" aria-label="BecaNexo">
        <Link className="brand" to="/" aria-label="BecaNexo, volver al inicio">BecaNexo</Link>
        <div className="brand-copy">
          <p className="brand-heading">Tu próximo paso <br />puede empezar <br />con una beca.</p>
          <p className="brand-description">Un espacio para conectar tu futuro<br className="hidden lg:block" /> con nuevas oportunidades.</p>
        </div>
      </aside>
      <main id="contenido" className="auth-main">
        <div className="auth-content">{children}</div>
        <footer className="auth-footer">BecaNexo · Proyecto de tesis · Avance inicial</footer>
      </main>
    </div>
  )
}
