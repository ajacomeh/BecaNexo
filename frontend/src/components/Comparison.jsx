import Icon from './Icon'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { safeReturnPath } from '../auth/returnPath'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'

const groups = [['cumple', 'Coincidencias declaradas'], ['no_cumple', 'Incumplimientos declarados'], ['desconocido', 'Información pendiente']]
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
    {condition.referencia_bases && <p>Referencia en las bases: {condition.referencia_bases}</p>}
  </li>
}

function Requirements({ items, catalogs }) {
  return groups.map(([state, title]) => {
    const records = items.filter(r => r.resultado === state)
    return records.length > 0 && <section key={state}><h4><Icon name={state === "cumple" ? "success" : state === "no_cumple" ? "failure" : "pending"} />{title}</h4><ul className="detail-list">{records.map(item => <Evaluation key={item.id} item={item} catalogs={catalogs} />)}</ul></section>
  })
}

function Option({ option, featured, catalogs }) {
  return <article className={`comparison-option comparison-${option.resultado}`}>
    {featured && <p className="eyebrow">OPCIÓN DESTACADA PARA CONSULTA</p>}
    <h3>{option.programa || 'Programa no especificado'}</h3>
    <p>{valueText(option.nivel)} · {valueText(option.modalidad)} · {option.destinos.join(', ') || 'Destino no especificado'}</p>
    <p className="comparison-summary"><Icon name={option.resultado === "cumple" ? "success" : option.resultado === "no_cumple" ? "failure" : "pending"} />{option.resumen}</p>
    {option.aviso && <Message kind="info">{option.aviso}</Message>}
    {option.verificaciones_externas_pendientes > 0 && <p className="comparison-external">Hay verificaciones externas pendientes, incluso cuando coinciden los datos declarados.</p>}
    {option.resultados_destino ? <div><h4>Resultado por destino</h4><p>Consulta las condiciones de cada país. Las preferencias de destino no determinan este resultado.</p>
      {option.resultados_destino.map((destino, index) => <details className={`comparison-destination comparison-${destino.resultado}`} key={destino.pais || 'desconocido'} open={index === 0}>
        <summary>{destino.nombre} · {destino.resumen}</summary><Requirements items={destino.requisitos} catalogs={catalogs} />
      </details>)}</div> : <Requirements items={option.requisitos} catalogs={catalogs} />}
  </article>
}

export default function Comparison({ offerId, catalogs }) {
  const { user } = useAuth()
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
  return <section className="profile-card comparison" aria-labelledby="comparison-title">
    <h2 id="comparison-title">Comparación de requisitos</h2>
    <p>Compara cada opción con tu información declarada. No acredita documentos ni garantiza admisión o adjudicación.</p>
    <Button icon={attempt ? "refresh" : "compare"} busy={state.busy} onClick={() => { setState({ data: null, busy: true, error: '' }); setAttempt(n => n + 1) }}>{state.busy ? 'Comparando requisitos…' : attempt ? 'Actualizar comparación' : 'Comparar requisitos'}</Button>
    {state.busy && <p role="status"><Icon name="loading" />Consultando requisitos y datos actuales…</p>}
    <Message>{state.error}</Message>
    {state.data && <div aria-live="polite">
      <p className="profile-note">{state.data.aviso}</p><p className="small-note">{state.data.criterio_destacada}</p>
      {!state.data.opciones.length && <Message kind="info">No hay opciones activas para comparar.</Message>}
      {state.data.opciones.filter(o => o.resultado !== 'no_cumple').map(option => <Option key={option.id} option={option} featured={option.id === state.data.opcion_destacada_id} catalogs={catalogs} />)}
      {state.data.opciones.some(o => o.resultado === 'no_cumple') && <section className="comparison-incompatible"><h3>Opciones con incumplimientos obligatorios</h3><p>Siguen disponibles para consulta. Puedes revisar tus datos y las bases oficiales.</p>{state.data.opciones.filter(o => o.resultado === 'no_cumple').map(option => <Option key={option.id} option={option} catalogs={catalogs} />)}</section>}
    </div>}
  </section>
}
