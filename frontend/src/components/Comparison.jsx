import Icon from './Icon'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { safeReturnPath } from '../auth/returnPath'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

const groups = [['cumple', 'Coincidencias declaradas'], ['no_cumple', 'Incumplimientos declarados'], ['desconocido', 'Información pendiente']]
const profileLinks = {
  'datos-personales': ['/perfil#datos-personales', 'Actualizar datos personales'],
  'formacion-academica': ['/perfil#formacion-academica', 'Actualizar formación académica'],
  idiomas: ['/preferencias#idiomas', 'Actualizar idiomas y niveles'],
  experiencia: ['/perfil#experiencia', 'Actualizar experiencia'],
  disponibilidad: ['/preferencias#disponibilidad', 'Actualizar disponibilidad'],
}
const labels = { nacionalidad: 'Nacionalidad', edad_a_fecha_referencia: 'Edad a la fecha de referencia', idioma: 'Idioma', nivel: 'Nivel', dedicacion: 'Dedicación', disponible_traslado: 'Disponibilidad de traslado', disponible_extranjero: 'Disponibilidad al extranjero', pais: 'País', provincia_residencia: 'Provincia', ciudad_residencia: 'Ciudad', estado_estudios: 'Estado de estudios', titulo_obtenido: 'Título obtenido', nombre_titulo: 'Nombre del título', area: 'Área', promedio: 'Promedio', escala_min: 'Mínimo de escala', escala_max: 'Máximo de escala' }
Object.assign(labels, { equivalencia_documentada: 'Referencia de equivalencia de título', equivalencia_provincia: 'Referencia de equivalencia de provincia', equivalencia_ciudad: 'Referencia de equivalencia de ciudad', periodos_sin_superposicion: 'Periodos sin superposición', fecha_corte: 'Fecha de corte' })
function valueText(value, key, catalogs, spec) {
  if (value == null) return 'No declarado'
  if (Array.isArray(value)) return value.map(v => valueText(v, key, catalogs, spec)).join(', ')
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (['pais', 'nacionalidad'].includes(key) || ['pais', 'paises'].includes(spec?.kind)) return catalogs.paises.find(p => p.codigo === value)?.nombre || String(value)
  if (key === 'idioma' || spec?.kind === 'idioma') return catalogs.idiomas.find(i => i.codigo === value)?.nombre || String(value)
  if (['area', 'areas'].includes(spec?.kind)) return catalogs.areas.find(a => a.id === value)?.nombre || String(value)
  return String(value).replaceAll('_', ' ')
}

function Evaluation({ item, catalogs }) {
  const type = catalogs.tipos_requisito.find(t => t.codigo === item.tipo)
  const condition = item.condicion_exigida
  return <li>
    <h5>{type?.nombre || item.tipo} · {item.obligatorio ? 'Obligatorio' : 'No obligatorio'}</h5>
    <p className="small-note">{item.ambito === 'comun' ? 'Requisito común' : item.ambito === 'destino' ? 'Requisito de este destino' : 'Requisito de esta opción'}{item.grupo_formacion && ` · Misma formación: ${item.grupo_formacion}`}</p>
    <p className="preserve-text">{item.descripcion}</p><p>{item.explicacion}</p>
    <dl className="detail-data">
      <div><dt>Dato declarado utilizado</dt><dd>{item.dato_declarado ? Object.entries(item.dato_declarado).map(([k, v]) => <p key={k}>{labels[k] || k}: {valueText(v, k, catalogs)}</p>) : 'Sin dato utilizado'}</dd></div>
      <div><dt>Condición exigida</dt><dd>{Object.entries(condition.valores || {}).map(([k, v]) => <p key={k}>{type?.esquema_valor?.campos[k]?.label || k}: {valueText(v, k, catalogs, type?.esquema_valor?.campos[k])}</p>)}{condition.fecha_referencia && <p>Fecha de referencia: {condition.fecha_referencia}</p>}</dd></div>
    </dl>
    {item.comprobacion_externa && <div className="comparison-external"><strong>Verificación externa pendiente</strong><p>La entidad oferente comprueba los documentos y certificados. La coincidencia declarada no los acredita.</p>{condition.documento && <p>{condition.documento}</p>}{condition.acreditacion && <p>{condition.acreditacion}</p>}</div>}
    {item.resultado !== 'cumple' && profileLinks[item.seccion_perfil] && <Link className="secondary-link comparison-profile-link" to={profileLinks[item.seccion_perfil][0]}><Icon name="profile" /><span>{profileLinks[item.seccion_perfil][1]}</span></Link>}
    {condition.referencia_bases && <p>Referencia en las bases: {condition.referencia_bases}</p>}
  </li>
}

function RequirementSummary({ items, result, title, catalogs }) {
  const counts = Object.fromEntries(groups.map(([state]) => [state, items.filter(item => item.resultado === state).length]))
  const names = Object.fromEntries(groups.map(([state]) => {
    const grouped = new Map()
    items.filter(item => item.resultado === state).forEach(item => {
      const name = catalogs.tipos_requisito.find(type => type.codigo === item.tipo)?.nombre || item.tipo
      grouped.set(name, (grouped.get(name) || 0) + 1)
    })
    return [state, [...grouped].map(([name, count]) => count > 1 ? `${name} (${count})` : name)]
  }))
  const explanation = !items.length ? 'No hay requisitos identificados para esta alternativa; no se confirma cumplimiento.'
    : result === 'no_cumple' ? 'Hay al menos un requisito obligatorio que no coincide con tus datos declarados.'
      : result === 'desconocido' ? 'Falta información para confirmar el cumplimiento de requisitos obligatorios.'
        : 'Los requisitos obligatorios comparables coinciden con tus datos declarados. Las verificaciones documentales siguen a cargo de la entidad oferente.'
  return <section className="comparison-overview" aria-label={title}>
    <h4>{title}</h4>
    <div className="comparison-counts">{groups.map(([state, label]) => <div className="comparison-count" key={state}>
      <p><strong>{counts[state]}</strong><span>{state === 'cumple' ? 'Cumplidos' : state === 'no_cumple' ? 'Incumplidos' : 'Sin información suficiente'}</span></p>
      <ul aria-label={label}>{names[state].length ? names[state].map(name => <li key={name}>{name}</li>) : <li>Ninguno</li>}</ul>
    </div>)}</div>
    <p>{explanation}</p>
    <p className="small-note">Se cuentan todos los requisitos de esta alternativa; el estado general considera los obligatorios. Esta comparación no predice adjudicación.</p>
  </section>
}

function Requirements({ items, catalogs }) {
  return groups.map(([state, title]) => {
    const records = items.filter(r => r.resultado === state)
    return records.length > 0 && <section key={state}><h4><Icon name={state === "cumple" ? "success" : state === "no_cumple" ? "failure" : "pending"} />{title}</h4><ul className="detail-list">{records.map(item => <Evaluation key={item.id} item={item} catalogs={catalogs} />)}</ul></section>
  })
}

function Option({ option, featured, catalogs, topSummarized = false, summarizedDestination = null }) {
  return <article className={`comparison-option comparison-${option.resultado}`}>
    {featured && <p className="eyebrow">OPCIÓN DESTACADA PARA CONSULTA</p>}
    <h3>{option.programa || 'Programa no especificado'}</h3>
    <p>{valueText(option.nivel)} · {valueText(option.modalidad)} · {option.destinos.join(', ') || 'Destino no especificado'}</p>
    <p className="comparison-summary"><Icon name={option.resultado === "cumple" ? "success" : option.resultado === "no_cumple" ? "failure" : "pending"} />{option.resumen}</p>
    {option.aviso && <Message kind="info">{option.aviso}</Message>}
    {option.verificaciones_externas_pendientes > 0 && <p className="comparison-external">Hay verificaciones externas pendientes, incluso cuando coinciden los datos declarados.</p>}
    {option.resultados_destino ? <div><h4>Resultado por destino</h4><p>Consulta las condiciones de cada país. Las preferencias de destino no determinan este resultado.</p>
      {option.resultados_destino.map((destino, index) => <details className={`comparison-destination comparison-${destino.resultado}`} key={destino.pais || 'desconocido'} open={destino === summarizedDestination || (!summarizedDestination && index === 0)}>
        <summary>{destino.nombre} · {destino.resumen}</summary>{destino !== summarizedDestination && <RequirementSummary items={destino.requisitos} result={destino.resultado} title={`Resumen para ${destino.nombre}`} catalogs={catalogs} />}<Requirements items={destino.requisitos} catalogs={catalogs} />
      </details>)}</div> : <>{!topSummarized && <RequirementSummary items={option.requisitos} result={option.resultado} title="Resumen de esta opción" catalogs={catalogs} />}<Requirements items={option.requisitos} catalogs={catalogs} /></>}
  </article>
}

export default function Comparison({ offerId, catalogs }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ data: null, busy: false, error: '' })
  useEffect(() => {
    if (!attempt || user?.rol !== 'postulante') return
    let live = true
    offersApi.get(`becas/${offerId}/comparacion`).then(data => { if (live) setState({ data, busy: false, error: '' }) })
      .catch(error => { if (live) setState({ data: null, busy: false, error: error.status === 404 ? 'Esta convocatoria ya no está disponible para comparar.' : error.message }) })
    return () => { live = false }
  }, [attempt, offerId, user?.rol, user?.id])
  useEffect(() => {
    if (!attempt) return
    const refresh = () => { setState({ data: null, busy: true, error: '' }); setAttempt(n => n + 1) }
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [attempt])
  if (user?.rol === 'administrador') return null
  if (!user) return <section className="profile-card"><h2>Compara los requisitos con tu información</h2><p>Inicia sesión para consultar coincidencias y datos pendientes. La entidad oferente verifica la documentación.</p><Link className="secondary-link" to={`/login?next=${encodeURIComponent(safeReturnPath(`/becas/${offerId}`))}`}><Icon name="compare" /><span>Iniciar sesión para comparar requisitos</span></Link></section>
  const selected = state.data?.opciones.find(option => option.id === state.data.opcion_destacada_id) || state.data?.opciones[0]
  const destination = selected?.resultados_destino?.find(item => item.resultado === selected.resultado)
  const summaryItems = destination?.requisitos || selected?.requisitos || []
  const actionableProfile = [...summaryItems].sort((a, b) => (a.resultado === 'no_cumple' ? 0 : 1) - (b.resultado === 'no_cumple' ? 0 : 1))
    .find(item => item.resultado !== 'cumple' && profileLinks[item.seccion_perfil]?.[0].startsWith('/perfil#'))
  const profilePath = actionableProfile ? profileLinks[actionableProfile.seccion_perfil][0] : '/perfil'
  return <section className="profile-card comparison" aria-labelledby="comparison-title">
    <h2 id="comparison-title">Comparación de requisitos</h2>
    <p>Compara cada opción con tu información declarada. No acredita documentos ni garantiza admisión o adjudicación.</p>
    <Button icon={attempt ? "refresh" : "compare"} busy={state.busy} onClick={() => { setState({ data: null, busy: true, error: '' }); setAttempt(n => n + 1) }}>{state.busy ? 'Comparando requisitos…' : attempt ? 'Actualizar comparación' : 'Comparar requisitos'}</Button>
    {state.busy && <p role="status"><Icon name="loading" />Consultando requisitos y datos actuales…</p>}
    <Message>{state.error}</Message>
    {state.data && <div aria-live="polite">
      <p className="profile-note">{state.data.aviso}</p><p className="small-note">{state.data.criterio_destacada}</p>
      {selected && <RequirementSummary items={summaryItems} result={selected.resultado} catalogs={catalogs}
        title={`Resumen superior: ${selected.programa || 'Programa no especificado'}${destination ? ` · ${destination.nombre}` : ''}`} />}
      <div className="comparison-summary-actions">
        <Button type="button" icon="profile" onClick={() => navigate(profilePath)}>Actualizar perfil</Button>
        <Button type="button" className="button-light" icon="preferences" onClick={() => navigate('/preferencias#preferencias')}>Actualizar preferencias</Button>
      </div>
      <p className="small-note">Las preferencias de estudio no determinan elegibilidad.</p>
      {!state.data.opciones.length && <Message kind="info">No hay opciones activas para comparar.</Message>}
      {state.data.opciones.filter(o => o.resultado !== 'no_cumple').map(option => <Option key={option.id} option={option} featured={option.id === state.data.opcion_destacada_id} catalogs={catalogs} topSummarized={option.id === selected?.id} summarizedDestination={option.id === selected?.id ? destination : null} />)}
      {state.data.opciones.some(o => o.resultado === 'no_cumple') && <section className="comparison-incompatible"><h3>Opciones con incumplimientos obligatorios</h3><p>Siguen disponibles para consulta. Puedes revisar tus datos y las bases oficiales.</p>{state.data.opciones.filter(o => o.resultado === 'no_cumple').map(option => <Option key={option.id} option={option} catalogs={catalogs} topSummarized={option.id === selected?.id} summarizedDestination={option.id === selected?.id ? destination : null} />)}</section>}
    </div>}
  </section>
}
