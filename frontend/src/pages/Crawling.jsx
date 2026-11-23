import Icon from '../components/Icon'
import { useEffect, useRef, useState } from 'react'
import { Link, Route, Routes, useParams, useLocation } from 'react-router-dom'
import { offersApi } from '../api/client'
import ProfileLayout from '../components/ProfileLayout'
import Button from '../components/Button'
import Message from '../components/Message'
import CrawlingControl from '../components/CrawlingControl'
import { estadoEjecucion } from './estadoEjecucion'
import ExecutionTabs from './ExecutionTabs'
import './Crawling.css'

const prefix = 'gestion/rastreo'
const labels = { parcial: 'Parcial', fallida: 'Fallida', ficha: 'Ficha', indice: 'Índice', bases: 'Bases', robots: 'Robots', BASE_NO_PERMITIDA: 'Bases fuera de la lista cerrada', BASE_INACCESIBLE: 'Bases inaccesibles', INDICE_LIMITE: 'Tope de fichas del índice', INDICE_ESTRUCTURA: 'Índice no interpretable', CANDIDATO_PENDIENTE: 'Candidato pendiente de revisión', CANDIDATO_FUERA_ALCANCE: 'Candidato fuera de alcance', BORRADOR_REVISION_PENDIENTE: 'Borrador con revisión pendiente', BORRADOR_AUTO_FALLIDO: 'Borrador automático fallido', FICHA_INCOMPLETA: 'Ficha incompleta', FICHA_FUERA_ALCANCE: 'Ficha fuera de alcance', ESTRUCTURA: 'HTML fuera de contrato', RED: 'Error de red', HTTP: 'Respuesta HTTP inesperada', ROBOTS: 'Bloqueo por robots.txt', REINTENTO_FUENTE: 'Reintento programado por la fuente', ALMACENAMIENTO: 'Error de almacenamiento', EJECUCION_FALLIDA: 'Ejecución fallida', INTERRUMPIDA: 'Ejecución interrumpida', OMITIDA: 'Omitida', nueva: 'Primera observación', sin_cambios: 'Sin cambios', cambio_bytes: 'Cambio técnico, sin cambios de contenido', cambio_relevante: 'Cambio relevante o de PDF', fallo: 'Fallo de acceso', reutilizado: 'Documento ya almacenado', descargado: 'Documento nuevo almacenado', error: 'Error', bloqueado: 'Acceso bloqueado', redirigido: 'Redirección', REVISION_DOCUMENTAL_PENDIENTE: 'Revisión documental pendiente', PDF_CAMBIADO: 'PDF cambiado; requiere revisión', titulo: 'Título', descripcion: 'Descripción', entidad_html: 'Entidad mencionada en HTML', beneficio: 'Beneficio', estudios: 'Estudios mencionados', requisitos: 'Requisitos', cierre: 'Cierre declarado en la fuente', fecha_publicacion: 'Fecha de publicación declarada', texto_original: 'Texto original', postulacion_y_documentos: 'Postulación externa y documentos', completa: 'Extracción HTML completa', advertencias: 'Advertencias' }
const label = (value) => labels[value] || String(value).replaceAll('_', ' ')
const date = (value) => value ? new Date(value).toLocaleString('es-EC') : 'No registrada'
const situationLabels = { borrador: 'Borrador privado', integrada: 'Borrador integrado', descartada: 'Descartada',
  sin_borrador: 'Sin borrador', sin_version: 'Sin versión', apta_sin_borrador: 'Apta para borrador' }
const situationLabel = (situation) => situationLabels[situation?.tipo] || 'Detectada'

// Borrador privado con sus indicadores; las demás situaciones conservan su etiqueta.
function SituationChips({ situation }) {
  if (situation?.tipo !== 'borrador') return <span className={`status-pill situation-${situation?.tipo || 'detectada'}`}>{situationLabel(situation)}</span>
  return <span className="crawl-situation-chips">
    <span className={`status-pill situation-${situation.descartado ? 'descartada' : 'borrador'}`}>{situation.descartado ? 'Borrador descartado' : 'Borrador privado'}</span>
    {situation.pendientes > 0 && <span className="status-pill situation-pendientes">Datos pendientes ({situation.pendientes})</span>}
    {situation.oferente_no_ecuatoriano && <span className="status-pill situation-oferente" title={situation.oferente_detectado || undefined}>Oferente no ecuatoriano</span>}
  </span>
}

function SituationNote({ situation }) {
  if (situation?.convocatoria_id) {
    return <p className="profile-note"><Link to={`/gestion/convocatorias/${situation.convocatoria_id}`}>Abrir borrador #{situation.convocatoria_id}</Link>{situation.oferente_detectado ? ` · Oferente detectado: ${situation.oferente_detectado}` : ''}</p>
  }
  return <p className="profile-note">{situation?.motivo || 'No es una convocatoria aprobada del catálogo.'}</p>
}

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
    <PageList key={JSON.stringify(filters)} title="Publicaciones detectadas" path="publicaciones" params={filters} render={(p) => <article className="crawl-publication"><div className="crawl-publication-heading"><h3><Link to={`publicaciones/${p.id}`}>{p.titulo}</Link></h3><SituationChips situation={p.situacion} /></div><p className="crawl-publication-source">{p.fuente.nombre}</p><p className="crawl-publication-url"><Origin url={p.url_original} /></p><dl className="crawl-publication-dates"><div><dt>Primera detección</dt><dd>{date(p.primera_deteccion)}</dd></div><div><dt>Última detección</dt><dd>{date(p.ultima_deteccion)}</dd></div></dl><div className="crawl-publication-footer"><SituationNote situation={p.situacion} /><Link className="secondary-link" to={`publicaciones/${p.id}`}><Icon name="detail" /><span>Abrir publicación</span></Link></div></article>} />
  </>
}

function TextData({ value }) {
  if (value === null || value === undefined || value === '') return <span className="small-note">Sin dato declarado</span>
  if (Array.isArray(value)) return value.length ? <ul className="crawl-evidence-list">{value.map((item, index) => <li key={index}><TextData value={item} /></li>)}</ul> : <span className="small-note">Sin datos</span>
  if (typeof value === 'object') {
    const entries = Object.entries(value)
    const missing = entries.filter(([, item]) => item === null || item === undefined || item === '' || (Array.isArray(item) && !item.length))
    const references = entries.filter(([key]) => !missing.some(([empty]) => empty === key) && /^(?:url|url_original|url_final|pagina_url|fuente_url|documento_url)$/i.test(key))
    const visible = entries.filter(([key]) => !missing.some(([empty]) => empty === key) && !references.some(([reference]) => reference === key))
    const fields = rows => <dl className="crawl-data">{rows.map(([key, item]) => <div key={key}><dt>{label(key)}</dt><dd><TextData value={item} /></dd></div>)}</dl>
    return <div className="crawl-evidence-object">{visible.length > 0 && fields(visible)}
      {references.length > 0 && <details><summary>Referencias de origen ({references.length})</summary>{fields(references)}</details>}
      {missing.length > 0 && <details><summary>Campos sin información ({missing.length})</summary><p className="small-note">{missing.map(([key]) => label(key)).join(' · ')}</p></details>}</div>
  }
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
  return <article className="crawl-document"><div className="crawl-document-heading"><h3>Evidencia {document.id} · {label(document.rol)}</h3>{document.mime && <span className="status-pill">{document.mime}</span>}</div><p className="small-note">{document.tamano_bytes} bytes · Documento conservado para comprobar el origen en Convocatorias.</p><details><summary>Datos técnicos</summary><p>SHA256: {document.sha256}</p><p>{document.url_original}</p></details><Button icon="download" busy={busy} onClick={download}>Descargar evidencia</Button><Message>{error}</Message></article>
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
    {[...groups.values()].map((group, index) => <article key={index} className="crawl-evidence"><h4>{label(group.funcion)} · {label(group.seccion)}</h4><p>{[...group.expressions].join(' · ')}</p><p className="crawl-text">{group.contexto_original}</p>{group.url && <Origin url={group.url} />}</article>)}
    {!groups.size && <p>Sin contextos académicos estructurados. Consulte la evidencia completa.</p>}
  </details>
}

function VersionContent({ version: v, focus }) {
  const heading = useRef(null)
  useEffect(() => { if (focus) heading.current?.focus() }, [focus])
  const data = v.datos_extraidos || {}
  const original = value => typeof value === 'string' ? value : value?.texto_original || value?.original
  const sections = [
    ['Información general', ['titulo', 'descripcion', 'entidad_html']],
    ['Fechas', ['cierre', 'fecha_publicacion']],
    ['Requisitos y cobertura', ['requisitos', 'beneficio']],
    ['Documentos, postulación y contacto', ['postulacion_y_documentos']],
  ]
  const section = ([title, keys]) => {
    const present = keys.filter(key => original(data[key]))
    return present.length ? <section key={title} className="crawl-evidence-group"><h4>{title}</h4><dl className="crawl-data">{present.map(key => <div key={key}><dt>{label(key)}</dt><dd className="crawl-text">{original(data[key])}{data[key]?.precision && <small>Precisión: {data[key].precision}</small>}</dd></div>)}</dl></section> : null
  }
  return <section className="profile-card crawl-version-content">
    <h2 ref={heading} tabIndex={-1}>Información extraída · versión {v.numero}</h2>
    <p className="small-note">Texto literal de la fuente. Las categorías sugeridas por IA y los datos desconocidos se revisan en Convocatorias; ninguna sugerencia queda confirmada aquí. Extracción: {label(v.estado_extraccion)}.</p>
    <div className="crawl-version-section">
    <p>Son menciones de la fuente, no requisitos u opciones confirmados. Se conserva el significado original de fechas y cantidades.</p>
    <div className="crawl-evidence-groups"><div className="crawl-evidence-column">{section(sections[0])}{section(sections[2])}
      {data.estudios && <section className="crawl-evidence-group"><h4>Modalidad y destino mencionados</h4><dl className="crawl-data">{['modalidad', 'destino'].map(key => original(data.estudios[key]) && <div key={key}><dt>{label(key)}</dt><dd>{original(data.estudios[key])}</dd></div>)}</dl><StudyEvidence studies={data.estudios} /></section>}</div>
      <div className="crawl-evidence-column">{section(sections[1])}{section(sections[3])}
        <section className="crawl-evidence-group"><h4>Enlaces de la ficha</h4>{[['Bases', data.enlaces_bases], ['Postulación externa', data.enlaces_postulacion]].map(([title, links]) => <div key={title}><strong>{title}</strong>{links?.length ? <ul>{links.map((link, index) => <li key={index}><Origin url={link.url} /></li>)}</ul> : <p>No consta en la extracción.</p>}</div>)}</section></div></div></div>
    <div className="crawl-version-section"><h3>Advertencias y datos por confirmar</h3><TextData value={v.advertencias} /></div>
  </section>
}

function VersionEvidence({ version: v }) {
  const data = v.datos_extraidos || {}
  const groups = [
    ['Datos generales', ['titulo', 'descripcion', 'entidad_html', 'oferentes', 'tipo_oportunidad']],
    ['Fechas', ['apertura', 'cierre', 'fecha_publicacion', 'vigencia_al_consultar']],
    ['Requisitos', ['requisitos', 'destinatarios']],
    ['Beneficios', ['beneficio', 'financiacion', 'cobertura']],
    ['Estudios, modalidad y destino', ['estudios']],
    ['Enlaces y documentos', ['enlaces_bases', 'enlaces_postulacion', 'postulacion_y_documentos', 'documentos']],
  ]
  const known = new Set(groups.flatMap(([, keys]) => keys))
  const rest = Object.keys(data).filter(key => !known.has(key))
  if (rest.length) groups.push(['Otros datos de procedencia', rest])
  return <><p className="small-note">Extracción HTML. Los documentos y las notas manuales conservan su procedencia; la descarga no acredita la aprobación de las bases.</p>
    <details><summary>Evidencia estructurada completa</summary><div className="crawl-structured-groups">{groups.map(([title, keys]) => {
      const values = Object.fromEntries(keys.filter(key => Object.hasOwn(data, key)).map(key => [key, data[key]]))
      return Object.keys(values).length ? <section className="crawl-structured-group" key={title}><h3>{title}</h3><TextData value={values} /></section> : null
    })}</div></details>
    <details><summary>Texto original completo</summary><p className="small-note">{v.version_extractor} · Contrato {v.version_contrato}</p><p className="crawl-original-text">{v.texto_extraido}</p></details></>
}

function Publication() {
  const { id } = useParams()
  const [selected, setSelected] = useState(null)
  return <><Link className="back-link crawl-publication-back" to="/gestion/rastreo"><Icon name="back" /><span>Volver a publicaciones</span></Link><Remote key={id} path={`publicaciones/${id}`}>
    {(p) => { const version = selected?.publication === id ? selected.version : p.version_observada_id
      const classification = p.clasificacion_borrador
      const draft = p.borrador
      const closure = p.cierre_extraido?.texto_original || p.cierre_extraido?.original
      return <><header className="profile-card crawl-detail-hero"><div className="crawl-detail-heading"><h2>{p.titulo}</h2><span className="status-pill">Publicación detectada</span></div>
        <span className="crawl-detail-source">Fuente: {p.fuente.nombre}</span>
        <dl className="crawl-detail-facts"><div><dt>Clasificación</dt><dd>{classification?.estado === 'apta' ? 'Apta para revisión' : classification?.estado === 'pendiente' ? 'Pendiente de verificar' : classification?.estado === 'fuera_alcance' ? 'Fuera de alcance' : 'Sin clasificar'}</dd></div><div><dt>Convocatoria vinculada</dt><dd>{draft ? draft.revision === 'validada' && draft.activa ? 'Publicada' : draft.revision === 'pendiente' ? 'Borrador privado' : 'Inactiva' : 'No generada'}</dd></div><div><dt>Primera detección</dt><dd>{date(p.primera_deteccion)}</dd></div><div><dt>Última detección</dt><dd>{date(p.ultima_deteccion)}</dd></div><div><dt>Cierre declarado</dt><dd>{closure || 'No identificado'}</dd></div><div className="crawl-detail-origin"><dt>Publicación original</dt><dd><Origin url={p.url_original} /></dd></div></dl>
        {draft ? <><div className="crawl-detail-pending"><strong>Pendientes importantes</strong>{draft.bloqueos?.length ? <ul>{draft.bloqueos.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <p>Sin bloqueos de procedencia detectados. Convocatorias comprueba los demás datos antes de publicar.</p>}{draft.observaciones?.length > 0 && <p className="small-note">Por revisar: {draft.observaciones.join(' · ')}</p>}</div><Link className="secondary-link crawl-draft-link" to={`/gestion/convocatorias/${draft.id}`}><Icon name="detail" /><span>Abrir borrador en Convocatorias</span></Link></>
          : <p className="crawl-detail-pending" role="status"><strong>Sin borrador:</strong> {classification?.motivo || 'No hay una versión con evidencia suficiente para prepararlo.'} La revisión de origen permanece disponible aquí.</p>}
        <p className="small-note">Una publicación detectada no equivale a una beca aprobada del catálogo.</p></header>
        {version ? <Remote key={`${id}:${version}`} path={`publicaciones/${id}/versiones/${version}`}>
          {(v) => <><VersionContent version={v} focus={selected?.publication === id} />
            <section className="profile-card crawl-evidence-panel"><h2>Evidencias y versiones</h2>
              <PageList key={id} title="Seleccionar versión" path={`publicaciones/${id}/versiones`} render={(row) => <div className={`crawl-version-row${Number(version) === row.id ? ' crawl-version-current' : ''}`}><div><strong>Versión {row.numero}</strong><span className="small-note">Registrada {date(row.creada_en)}</span></div>{Number(version) === row.id ? <span className="crawl-selected">Versión seleccionada</span> : <Button icon="detail" onClick={() => setSelected({ publication: id, version: row.id })}>Consultar versión {row.numero}</Button>}</div>} />
              <details><summary>Documentos asociados</summary><PageList key={`docs:${id}:${version}`} title="Documentos de esta versión" path={`publicaciones/${id}/versiones/${version}/documentos`} render={(d) => <Download document={d} />} /></details>
              <VersionEvidence version={v} /></section></>}
        </Remote> : <section className="profile-card"><h2>Información extraída</h2><p>No hay una versión conservada para esta publicación.</p></section>}
        <section className="crawl-history"><PageList key={`obs:${id}`} title="Historial" path={`publicaciones/${id}/observaciones`} render={(o) => <div>{date(o.observada_en)} · {label(o.resultado)} · Versión ID {o.version_id || 'No disponible'}<p><Link to={`/gestion/rastreo/ejecuciones/${o.ejecucion_id}`}>Consultar ejecución {o.ejecucion_id}</Link> · {label(o.estado_ejecucion)}</p></div>} /></section>
      </> }}
  </Remote></>
}

function Candidate({ item }) {
  return <article className="crawl-publication crawl-candidate"><div className="crawl-publication-heading"><h3>{item.titulo}</h3><span className="status-pill">Pendiente</span></div>
    <p className="crawl-publication-source">{item.fuente}</p><p className="crawl-publication-url"><Origin url={item.url} /></p>
    <dl className="crawl-publication-dates"><div><dt>Primera detección</dt><dd>{date(item.primera_deteccion)}</dd></div><div><dt>Última detección</dt><dd>{date(item.ultima_deteccion)}</dd></div><div><dt>Página de origen</dt><dd>{item.pagina}</dd></div><div><dt>Ejecución de registro</dt><dd><Link to={`/gestion/rastreo/ejecuciones/${item.ejecucion_id}`}>Ejecución {item.ejecucion_id}</Link></dd></div></dl>
  </article>
}

function Candidates({ execution }) {
  return <><p className="crawl-detail-warning">Estos registros son enlaces detectados automáticamente. Todavía no constituyen convocatorias verificadas ni publicadas.</p>
    <PageList key={execution || 'all'} title={execution ? 'Candidatos registrados en esta ejecución' : 'Candidatos del índice'} path="candidatos-indice" params={execution ? { ejecucion: execution } : {}} render={(item) => <Candidate item={item} />} /></>
}

function ExecutionInfo({ item }) {
  const metadata = item.tipo === 'metadatos_indice'
  const documentaryMetrics = <dl className="crawl-metrics"><div><dt>{metadata ? 'Accesos documentales registrados' : 'Accesos HTTP (incluye intentos)'}</dt><dd>{item.accesos}</dd></div><div><dt>Documentos distintos de esta ejecución</dt><dd>{item.documentos_distintos}</dd></div><div><dt>Publicaciones observadas</dt><dd>{item.publicaciones_observadas}</dd></div><div><dt>Versiones nuevas</dt><dd>{item.versiones_con_cambios ?? item.versiones_nuevas}</dd></div><div><dt>Observaciones sin cambios</dt><dd>{item.observaciones_sin_cambios}</dd></div>{item.cambios_tecnicos > 0 && <div><dt>Cambio técnico, sin cambios de contenido</dt><dd>{item.cambios_tecnicos}</dd></div>}</dl>
  return <><p>{item.fuente.nombre} · {estadoEjecucion(item.estado, item.incidencias_aviso)}</p>{metadata && <p className="crawl-detail-warning"><strong>Descubrimiento de metadatos.</strong> Se registraron {item.candidatos_registrados} candidatos de índice. No se descargaron fichas ni documentos; las consultas al índice no se detallan como accesos documentales.</p>}<p>Inicio: {date(item.inicio)} · Fin: {date(item.fin)}</p>{metadata ? <><dl className="crawl-metrics"><div><dt>Candidatos registrados</dt><dd>{item.candidatos_registrados}</dd></div></dl><details><summary>Métricas documentales de esta ejecución</summary>{documentaryMetrics}</details></> : documentaryMetrics}</>
}

function Execution() {
  const { id } = useParams()
  return <><Link to="/gestion/rastreo/ejecuciones"><Icon name="back" /><span>Volver a ejecuciones</span></Link><h2>Ejecución {id}</h2><Remote key={id} path={`ejecuciones/${id}`}>{(e) => <><ExecutionInfo item={e} />{e.tipo === 'metadatos_indice' ? <Candidates execution={id} /> : <p>Una ejecución completada no aprueba documentos. Los documentos distintos pueden incluir evidencia almacenada anteriormente.</p>}
    <ExecutionTabs key={id} execution={id} item={e} label={label} /></>}</Remote>
  </>
}

export default function Crawling() {
  const { pathname } = useLocation()
  const executions = pathname.includes("/ejecuciones")
  const candidates = pathname.includes("/candidatos-indice")
  return <ProfileLayout><div className="crawl"><h1>Rastreo</h1><p>Consulta publicaciones y evidencias detectadas por fuentes autorizadas. La revisión y publicación se completan en Convocatorias.</p><nav className="heading-actions crawl-tabs" aria-label="Secciones de rastreo"><Link aria-current={!executions && !candidates ? "page" : undefined} to="/gestion/rastreo">Publicaciones detectadas</Link><Link aria-current={executions ? "page" : undefined} to="/gestion/rastreo/ejecuciones">Ejecuciones</Link><Link aria-current={candidates ? "page" : undefined} to="/gestion/rastreo/candidatos-indice">Candidatos del índice</Link></nav>
    <Routes><Route index element={<Publications />} /><Route path="publicaciones/:id" element={<Publication />} /><Route path="candidatos-indice" element={<Candidates />} /><Route path="ejecuciones" element={<PageList title="Ejecuciones" path="ejecuciones" render={(e) => <div><h3><Link to={`/gestion/rastreo/ejecuciones/${e.id}`}>Ejecución {e.id}</Link></h3><ExecutionInfo item={e} /><Link className="secondary-link" to={`/gestion/rastreo/ejecuciones/${e.id}`}><Icon name="detail" /><span>Ver detalle de ejecución</span></Link></div>} />} /><Route path="ejecuciones/:id" element={<Execution />} /><Route path="*" element={<p>Ruta de rastreo no encontrada.</p>} /></Routes>
  </div></ProfileLayout>
}
