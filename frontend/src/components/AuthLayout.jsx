export default function AuthLayout({ children }) {
  return (
    <div className="auth-layout">
      <aside className="brand-panel" aria-label="BecaNexo">
        <span className="brand">BecaNexo</span>
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
