import Icon from '../components/Icon'
import { useEffect, useRef, useState } from 'react'
import { Link, Route, Routes, useParams, useLocation } from 'react-router-dom'
import { offersApi } from '../api/client'
import ProfileLayout from '../components/ProfileLayout'
import Button from '../components/Button'
import Message from '../components/Message'
import CrawlingReviews from '../components/CrawlingReviews'
import CrawlingProposal from '../components/CrawlingProposal'
import CrawlingControl from '../components/CrawlingControl'
import './Crawling.css'

const prefix = 'gestion/rastreo'
const labels = { finalizada: 'Descarga finalizada', parcial: 'Descarga parcial', fallida: 'Descarga fallida', en_curso: 'En curso', omitida: 'Omitida', nueva: 'Primera observación', sin_cambios: 'Sin cambios', cambio_bytes: 'Cambio de evidencia sin diferencia relevante detectada', cambio_relevante: 'Cambio relevante o de PDF', fallo: 'Fallo de acceso', reutilizado: 'Documento ya almacenado', descargado: 'Documento nuevo almacenado', error: 'Error', bloqueado: 'Acceso bloqueado', redirigido: 'Redirección', REVISION_DOCUMENTAL_PENDIENTE: 'Revisión documental pendiente', PDF_CAMBIADO: 'PDF cambiado; requiere revisión', titulo: 'Título', descripcion: 'Descripción', entidad_html: 'Entidad mencionada en HTML', beneficio: 'Beneficio', estudios: 'Estudios mencionados', requisitos: 'Requisitos', cierre: 'Cierre declarado en la fuente', fecha_publicacion: 'Fecha de publicación declarada', texto_original: 'Texto original', postulacion_y_documentos: 'Postulación externa y documentos', completa: 'Extracción HTML completa', advertencias: 'Advertencias' }
const label = (value) => labels[value] || String(value).replaceAll('_', ' ')
const date = (value) => value ? new Date(value).toLocaleString('es-EC') : 'No registrada'

function Remote({ path, params = {}, children }) {
  const [state, setState] = useState({ loading: true })
  const [retry, setRetry] = useState(0)
  const query = JSON.stringify(params)
  useEffect(() => {
    let live = true
    offersApi.get(`${prefix}/${path}`, JSON.parse(query)).then((data) => { if (live) setState({ data }) }).catch((error) => { if (live) setState({ error: error.message }) })
    return () => { live = false }
  }, [path, query, retry])
  if (state.error) return <><Message>{state.error}</Message><Button icon="refresh" type="button" onClick={() => { setState({ loading: true }); setRetry(retry + 1) }}>Reintentar</Button></>
  if (state.loading) return <p role="status"><Icon name="loading" />Cargando información de rastreo…</p>
  return children(state.data)
}

function PageList({ path, params = {}, render, title }) {
  const [page, setPage] = useState(1)
  return <section className="profile-card"><h2>{title}</h2><Remote key={`${path}:${JSON.stringify(params)}:${page}`} path={path} params={{ ...params, page }}>
    {(data) => <>{data.results.length ? <ul className="record-list crawl-list">{data.results.map((item) => <li key={item.id}>{render(item)}</li>)}</ul> : <p>No hay registros para esta consulta.</p>}
      {data.count <= data.page_size ? <p className="crawl-count">{data.count} {data.count === 1 ? 'registro' : 'registros'}</p> : <nav className="pagination" aria-label={`Paginación de ${title}`}><Button icon="previous" disabled={page <= 1} onClick={() => setPage(page - 1)}>Anterior</Button><span>Página {page} de {Math.ceil(data.count / data.page_size)} · {data.count} registros</span><Button icon="next" disabled={page * data.page_size >= data.count} onClick={() => setPage(page + 1)}>Siguiente</Button></nav>}</>}
  </Remote></section>
}

function Origin({ url }) {
  let valid = false
  try { const parsed = new URL(url); valid = ['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password } catch { /* Solo texto cuando no es un enlace seguro. */ }
  return valid ? <a href={url} target="_blank" rel="noopener noreferrer">{url}</a> : <span>{url}</span>
}

function SourceFilter({ value, onChange }) {
  const [page, setPage] = useState(1)
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState({ options: [], loading: true, more: false, error: '' })
  useEffect(() => {
    let live = true
    offersApi.get(`${prefix}/fuentes`, { page, page_size: 50 }).then(data => {
      if (live) setState(previous => ({ options: [...new Map([...previous.options, ...data.results].map(f => [f.id, f])).values()], loading: false, more: page * data.page_size < data.count, error: '' }))
    }).catch(error => { if (live) setState(previous => ({ ...previous, loading: false, error: error.message })) })
    return () => { live = false }
  }, [page, retry])
  return <div className="crawl-source"><label htmlFor="crawl-source">Fuente</label><select id="crawl-source" name="fuente" value={value} onChange={event => onChange(event.target.value)}><option value="">Todas las fuentes</option>{state.options.map(f => <option key={f.id} value={f.id}>{f.nombre}</option>)}</select>
    {state.loading && <span role="status"><Icon name="loading" />Cargando fuentes…</span>}{state.error && <><Message>{state.error}</Message><Button icon="refresh" type="button" onClick={() => { setState(s => ({ ...s, loading: true, error: '' })); setRetry(retry + 1) }}>Reintentar fuentes</Button></>}
    {state.more && !state.error && <Button icon="add" type="button" busy={state.loading} onClick={() => { setState(s => ({ ...s, loading: true })); setPage(page + 1) }}>Más fuentes</Button>}
  </div>
}

function Publications() {
  const [filters, setFilters] = useState({})
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('')
  return <><CrawlingControl /><form className="profile-card crawl-filters" onSubmit={(event) => {
    event.preventDefault()
    setFilters({ q: query, ...(source ? { fuente: source } : {}) })
  }}><label htmlFor="crawl-query">Buscar título o URL<input id="crawl-query" name="q" maxLength={200} type="search" value={query} onChange={event => setQuery(event.target.value)} /></label><SourceFilter value={source} onChange={setSource} /><div className="crawl-filter-actions"><Button icon="search" type="submit">Buscar</Button>{(query || source || filters.q || filters.fuente) && <Button icon="clear" className="button-light" type="button" onClick={() => { setQuery(''); setSource(''); setFilters({}) }}>Limpiar</Button>}</div></form>
    <PageList key={JSON.stringify(filters)} title="Publicaciones detectadas" path="publicaciones" params={filters} render={(p) => <article className="crawl-publication"><div className="crawl-publication-heading"><h3><Link to={`publicaciones/${p.id}`}>{p.titulo}</Link></h3><span className="status-pill">Detectada</span></div><p className="crawl-publication-source">{p.fuente.nombre}</p><p className="crawl-publication-url"><Origin url={p.url_original} /></p><dl className="crawl-publication-dates"><div><dt>Primera detección</dt><dd>{date(p.primera_deteccion)}</dd></div><div><dt>Última detección</dt><dd>{date(p.ultima_deteccion)}</dd></div></dl><div className="crawl-publication-footer"><p className="profile-note">No es una convocatoria aprobada del catálogo.</p><Link className="secondary-link" to={`publicaciones/${p.id}`}><Icon name="detail" /><span>Abrir publicación</span></Link></div></article>} />
  </>
}

function TextData({ value }) {
  if (value === null || value === undefined || value === '') return <span>No declarado</span>
  if (Array.isArray(value)) return value.length ? <ul>{value.map((item, index) => <li key={index}><TextData value={item} /></li>)}</ul> : <span>Sin datos</span>
  if (typeof value === 'object') return <dl className="crawl-data">{Object.entries(value).map(([key, item]) => <div key={key}><dt>{label(key)}</dt><dd><TextData value={item} /></dd></div>)}</dl>
  return <span className="crawl-text">{typeof value === 'boolean' ? (value ? 'Sí' : 'No') : String(value)}</span>
}

function Download({ document }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function download() {
    if (busy) return
    setBusy(true); setError('')
    try {
      const response = await fetch(`/api/${prefix}/documentos/${document.id}/descarga/`, { credentials: 'same-origin', cache: 'no-store' })
      if (!response.ok) throw new Error(response.status === 409 ? 'Evidencia no disponible o inconsistente.' : 'No se pudo descargar la evidencia. Comprueba tu sesión e inténtalo de nuevo.')
      const url = URL.createObjectURL(await response.blob())
      const link = window.document.createElement('a')
      link.href = url; link.download = `evidencia-${document.id}.${document.mime === 'application/pdf' ? 'pdf' : document.mime === 'text/html' ? 'html' : 'txt'}`
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }
  return <div><h3>Evidencia {document.id} · {label(document.rol)}</h3><p>{document.mime} · {document.tamano_bytes} bytes</p><details><summary>Datos técnicos</summary><p>SHA256: {document.sha256}</p><p>{document.url_original}</p></details><Button icon="download" busy={busy} onClick={download}>Descargar evidencia</Button><Message>{error}</Message></div>
}


function StudyEvidence({ studies }) {
  const groups = new Map()
  for (const mention of studies.menciones_academicas || []) {
    const key = JSON.stringify([mention.url, mention.seccion, mention.funcion, mention.contexto_original])
    if (!groups.has(key)) groups.set(key, { ...mention, expressions: new Set() })
    groups.get(key).expressions.add(mention.expresion_original)
  }
  return <details><summary>Estudios y contextos mencionados</summary>
    <p>Estas menciones no asignan niveles ni crean opciones de estudio.</p>
    {['destino', 'modalidad'].map(key => studies[key]?.texto_original && <p key={key}>{label(key)}: {studies[key].texto_original}</p>)}
    {[...groups.values()].map((group, index) => <article key={index} className="crawl-evidence"><h4>{label(group.funcion)} · {label(group.seccion)}</h4><p>{[...group.expressions].join(' · ')}</p><p className="crawl-text">{group.contexto_original}</p>{group.url && <Origin url={group.url} />}</article>)}
    {!groups.size && <p>Sin contextos académicos estructurados. Consulte la evidencia completa.</p>}
  </details>
}

function VersionContent({ version: v, focus }) {
  const heading = useRef(null)
  useEffect(() => { if (focus) heading.current?.focus() }, [focus])
  const data = v.datos_extraidos || {}
  const original = value => typeof value === 'string' ? value : value?.texto_original || value?.original
  return <section className="profile-card">
    <h2 ref={heading} tabIndex={-1}>Información de la versión {v.numero}</h2>
    <h3>Resumen</h3><p>{label(v.estado_extraccion)} · Consulte las decisiones documentales de esta versión en Revisiones administrativas.</p>
    <p>Procedencia: extracción HTML. No acredita documentos ni aprobación de las bases PDF. Las notas manuales documentales conservan su autoría; no son extracción automática.</p>
    <h3>Información extraída</h3>
    <p>Son menciones de la fuente, no requisitos u opciones confirmados. Se conserva el significado original de fechas y cantidades.</p>
    <dl className="crawl-data">{['titulo', 'descripcion', 'entidad_html', 'beneficio', 'cierre', 'fecha_publicacion', 'requisitos', 'postulacion_y_documentos'].map(key => original(data[key]) ? <div key={key}><dt>{label(key)}</dt><dd className="crawl-text">{original(data[key])}{data[key]?.precision && <p>Precisión: {data[key].precision}</p>}</dd></div> : null)}</dl>
    {data.estudios && <StudyEvidence studies={data.estudios} />}
    <h3>Advertencias y ambigüedades</h3><TextData value={v.advertencias} />
    <details><summary>Evidencia estructurada completa</summary><p>Incluye los contextos y referencias originales, también cuando se repiten.</p><TextData value={data} /></details>
    <details><summary>Texto pertinente y versión del extractor</summary><p>{v.version_extractor} · Contrato {v.version_contrato}</p><p className="crawl-text">{v.texto_extraido}</p></details>
  </section>
}

function Publication() {
  const { id } = useParams()
  const [selected, setSelected] = useState(null)
  return <><Link to="/gestion/rastreo"><Icon name="back" /><span>Volver a publicaciones</span></Link><Remote key={id} path={`publicaciones/${id}`}>
    {(p) => { const version = selected?.publication === id ? selected.version : p.version_observada_id
      return <><h2>{p.titulo}</h2><p>{p.fuente.nombre} · Publicación detectada, no publicada en el catálogo</p><Origin url={p.url_original} /><p>Primera detección: {date(p.primera_deteccion)} · Última detección: {date(p.ultima_deteccion)}</p>
        <p>La selección inicial corresponde a la última observación exitosa. Una versión anterior puede haberse observado de nuevo.</p>
        <PageList key={id} title="Versiones registradas" path={`publicaciones/${id}/versiones`} render={(v) => <div>Versión {v.numero} · Registrada {date(v.creada_en)} <>{Number(version) === v.id ? <span className="crawl-selected">Versión seleccionada</span> : <Button icon="detail" onClick={() => setSelected({ publication: id, version: v.id })}>Consultar versión {v.numero}</Button>}</></div>} />
        {version && <Remote key={`${id}:${version}`} path={`publicaciones/${id}/versiones/${version}`}>
          {(v) => <VersionContent version={v} focus={selected?.publication === id} />}
        </Remote>}
        {version && <PageList key={`docs:${id}:${version}`} title="Documentos de esta versión" path={`publicaciones/${id}/versiones/${version}/documentos`} render={(d) => <Download document={d} />} />}
        {version && <CrawlingReviews key={`reviews:${id}:${version}`} publication={id} version={version} />}
        <CrawlingProposal key={`proposal:${id}`} publication={id} />
        <PageList key={`obs:${id}`} title="Historial de observaciones" path={`publicaciones/${id}/observaciones`} render={(o) => <div>{date(o.observada_en)} · {label(o.resultado)} · Versión ID {o.version_id || 'No disponible'}<p><Link to={`/gestion/rastreo/ejecuciones/${o.ejecucion_id}`}>Consultar ejecución {o.ejecucion_id}</Link> · {label(o.estado_ejecucion)}</p></div>} />
      </> }}
  </Remote></>
}

function ExecutionInfo({ item }) {
  return <><p>{item.fuente.nombre} · {label(item.estado)}</p><p>Inicio: {date(item.inicio)} · Fin: {date(item.fin)}</p><dl className="crawl-metrics"><div><dt>Accesos HTTP (incluye intentos)</dt><dd>{item.accesos}</dd></div><div><dt>Documentos distintos de esta ejecución</dt><dd>{item.documentos_distintos}</dd></div><div><dt>Publicaciones observadas</dt><dd>{item.publicaciones_observadas}</dd></div><div><dt>Versiones nuevas</dt><dd>{item.versiones_nuevas}</dd></div><div><dt>Observaciones sin cambios</dt><dd>{item.observaciones_sin_cambios}</dd></div></dl></>
}

function Execution() {
  const { id } = useParams()
  return <><Link to="/gestion/rastreo/ejecuciones"><Icon name="back" /><span>Volver a ejecuciones</span></Link><h2>Ejecución {id}</h2><Remote key={id} path={`ejecuciones/${id}`}>{(e) => <ExecutionInfo item={e} />}</Remote>
    <p>Una descarga finalizada no aprueba documentos. Los documentos distintos pueden incluir evidencia almacenada anteriormente.</p>
    <PageList key={`access:${id}`} title="Accesos" path={`ejecuciones/${id}/accesos`} render={(a) => <div><p>{label(a.rol)} · HTTP {a.http_status || 'Sin respuesta'} · {label(a.resultado)}</p><Origin url={a.url_original} /><p>Inicio de petición: {date(a.inicio_peticion_en)} · Fin: {date(a.fin)}</p>{a.publicacion_id && <Link to={`/gestion/rastreo/publicaciones/${a.publicacion_id}`}>Publicación {a.publicacion_id}</Link>}</div>} />
    <PageList key={`issues:${id}`} title="Incidencias" path={`ejecuciones/${id}/incidencias`} render={(i) => <div><h3>{label(i.codigo)}</h3><p>{label(i.gravedad)} · {date(i.detectada_en)}</p></div>} />
  </>
}

export default function Crawling() {
  const { pathname } = useLocation()
  const executions = pathname.includes("/ejecuciones")
  return <ProfileLayout><div className="crawl"><h1>Rastreo</h1><p>Consulta de evidencia existente. Las publicaciones detectadas no son ofertas aprobadas para el catálogo.</p><nav className="heading-actions crawl-tabs" aria-label="Secciones de rastreo"><Link aria-current={!executions ? "page" : undefined} to="/gestion/rastreo">Publicaciones detectadas</Link><Link aria-current={executions ? "page" : undefined} to="/gestion/rastreo/ejecuciones">Ejecuciones</Link></nav>
    <Routes><Route index element={<Publications />} /><Route path="publicaciones/:id" element={<Publication />} /><Route path="ejecuciones" element={<PageList title="Ejecuciones" path="ejecuciones" render={(e) => <div><h3><Link to={`/gestion/rastreo/ejecuciones/${e.id}`}>Ejecución {e.id}</Link></h3><ExecutionInfo item={e} /><Link className="secondary-link" to={`/gestion/rastreo/ejecuciones/${e.id}`}><Icon name="detail" /><span>Ver detalle de ejecución</span></Link></div>} />} /><Route path="ejecuciones/:id" element={<Execution />} /><Route path="*" element={<p>Ruta de rastreo no encontrada.</p>} /></Routes>
  </div></ProfileLayout>
}
