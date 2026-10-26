import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'

function Actions({ user }) {
  return <div className="welcome-actions">
    <Link className="button" to="/becas">Explorar becas <span aria-hidden="true">↗</span></Link>
    <Link className="secondary-link" to={user ? '/inicio' : '/registro'}>{user ? 'Mi panel' : 'Crear cuenta'}</Link>
  </div>
}

const benefits = [
  ['Consulta requisitos y beneficios en un mismo lugar.', 'Conoce qué ofrece cada convocatoria y qué solicita la entidad oferente.'],
  ['Organiza tu información académica.', 'Reúne tus estudios, idiomas y preferencias en tu perfil personal.'],
  ['Guarda tus becas favoritas.', 'Vuelve a las oportunidades que te interesan cuando quieras consultarlas.'],
]
const steps = ['Explora las convocatorias.', 'Consulta requisitos y destinos.', 'Crea una cuenta para guardar tus favoritas.', 'Continúa la postulación en el sitio oficial de la entidad.']

export default function Welcome() {
  const { user } = useAuth()
  return <div className="welcome">
    <header className="welcome-header">
      <Link className="brand" to="/" aria-label="BecaNexo, inicio">BecaNexo<span aria-hidden="true">.</span></Link>
      <nav aria-label="Navegación principal">
        <Link to="/becas">Explorar becas</Link>
        {user ? <Link className="button" to="/inicio">Mi panel</Link> : <>
          <Link to="/login">Iniciar sesión</Link>
          <Link className="button" to="/registro">Crear cuenta</Link>
        </>}
      </nav>
    </header>
    <main id="contenido">
      <section className="welcome-hero" aria-labelledby="welcome-title">
        <div>
          <p className="eyebrow">TU SIGUIENTE ETAPA EMPIEZA AQUÍ</p>
          <h1 id="welcome-title">Encuentra oportunidades para <span>continuar tus estudios</span></h1>
          <p className="welcome-description">Explora becas ofrecidas por entidades ecuatorianas para estudiar en Ecuador o en el extranjero. Consulta sus requisitos, conoce sus beneficios y guarda las oportunidades que te interesan.</p>
          <Actions user={user} />
          <p className="welcome-note">Explora el catálogo sin crear una cuenta.</p>
        </div>
        <div className="welcome-art">
          <p className="eyebrow">UN NUEVO CAPÍTULO PARA TU FUTURO</p>
          <svg viewBox="0 0 440 310" aria-hidden="true" focusable="false">
            <circle cx="220" cy="152" r="126" fill="#244970" />
            <circle cx="220" cy="152" r="103" fill="none" stroke="#7798b7" strokeDasharray="4 9" />
            <path d="M62 250h100v-40h98v-40h112" fill="none" stroke="#48c6c3" strokeWidth="12" strokeLinejoin="round" />
            <path d="M352 151l22 19-22 19" fill="none" stroke="#48c6c3" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M103 124q59-18 117 8 58-26 117-8v102q-58-18-117 9-59-27-117-9z" fill="#f5f7fb" stroke="#b7cce2" strokeWidth="3" />
            <path d="M220 134v99M126 152l67 10m-67 12 67 10m-67 12 43 7m78-41 67-10m-67 32 67-10m-67 32 43-7" stroke="#9eb5ce" strokeWidth="4" strokeLinecap="round" />
            <path d="M145 91l75-36 75 36-75 35z" fill="#48c6c3" />
            <path d="M174 108v24q46 25 92 0v-24l-46 22z" fill="#1599a5" />
            <path d="M295 92v46" stroke="#f4cc72" strokeWidth="4" strokeLinecap="round" />
            <circle cx="295" cy="142" r="6" fill="#f4cc72" />
            <path d="M76 78v20m-10-10h20m264-27v16m-8-8h16" stroke="#f4cc72" strokeWidth="3" strokeLinecap="round" />
            <circle cx="354" cy="250" r="6" fill="#48c6c3" />
          </svg>
          <div className="welcome-art-caption"><strong>Tu próximo paso empieza con información.</strong><p>Conoce las oportunidades. Elige tu camino.</p></div>
        </div>
      </section>
      <section className="welcome-section" aria-labelledby="benefits-title">
        <p className="eyebrow">EXPLORA · ORGANIZA · GUARDA</p>
        <h2 id="benefits-title">Más claridad para dar el siguiente paso</h2>
        <div className="welcome-benefits">{benefits.map(([title, description], index) => <article key={title}>
          <span className="welcome-number" aria-hidden="true">0{index + 1}</span><h3>{title}</h3><p>{description}</p>
        </article>)}</div>
      </section>
      <section className="welcome-section welcome-how" aria-labelledby="how-title">
        <div><p className="eyebrow">A TU RITMO</p><h2 id="how-title">Cómo funciona</h2><p>Desde la primera consulta hasta el sitio oficial, tú decides el siguiente paso.</p></div>
        <ol>{steps.map((step) => <li key={step}>{step}</li>)}</ol>
      </section>
      <section className="welcome-closing" aria-labelledby="closing-title">
        <p className="eyebrow">DA EL PRIMER PASO</p><h2 id="closing-title">Tu próxima oportunidad está por descubrir</h2>
        <p>Explora las convocatorias y crea tu espacio para guardar las que te interesan.</p>
        <Actions user={user} />
      </section>
    </main>
    <footer className="welcome-footer"><Link className="brand" to="/">BecaNexo</Link><p>La postulación y la adjudicación corresponden a las entidades oferentes. BecaNexo facilita la consulta de oportunidades.</p></footer>
  </div>
}
