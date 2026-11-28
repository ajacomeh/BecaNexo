import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Message from '../components/Message'
import Button from '../components/Button'
import FavoriteButton from '../components/FavoriteButton'
import Comparison from '../components/Comparison'
import SimilarOffers from '../components/SimilarOffers'
import { display, date, dayDate, stateLabel, closingText, publishedPeriod, providerLabel } from './offerDisplay'
import { readable, unique, benefitSummary } from './catalogPresentation'
import { fieldLabel } from './offerFields'

export function BenefitList({ records, nested = false }) {
  const Heading = nested ? 'h4' : 'h3'
  return records.length ? <ul className="detail-list benefit-list">{records.map((b) => <li key={b.id}><Heading>{b.concepto}</Heading>
    {b.porcentaje != null && <p>Porcentaje del concepto financiado: {b.porcentaje} %</p>}
    {b.monto != null && <p>Importe fijo: {b.monto} {b.moneda}</p>}
    {b.tope_original && <p>Tope según las bases: {b.tope_original}{b.tope_monto != null && b.tope_moneda ? ` · Límite revisado: ${b.tope_monto} ${b.tope_moneda}` : ' · Moneda no confirmada o valor pendiente de revisión'}</p>}
    {b.periodicidad && <p>Periodicidad: {b.periodicidad}</p>}{b.detalle && <p className="preserve-text">{b.detalle}</p>}</li>)}</ul> : <p>No especificado</p>
}

function ruleText(value, spec, catalogs) {
  if (value == null) return 'No especificado'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  const one = (v) => {
    if (['paises', 'pais'].includes(spec?.kind)) return catalogs.paises.find((x) => x.codigo === v)?.nombre || String(v)
    if (['areas', 'area'].includes(spec?.kind)) return catalogs.areas.find((x) => x.id === v)?.nombre || String(v)
    if (spec?.kind === 'idioma') return catalogs.idiomas.find((x) => x.codigo === v)?.nombre || String(v)
    return String(v).replaceAll('_', ' ')
  }
  return Array.isArray(value) ? value.map(one).join(', ') : one(value)
}

export function RequirementList({ records, catalogs, nested = false }) {
  const Heading = nested ? 'h4' : 'h3'
  const sharedVerification = records.length > 1 && records.every(r => r.modo_comprobacion === records[0].modo_comprobacion)
  const academicGroups = [...new Set(records.map(r => r.grupo_formacion).filter(Boolean))]
  const groupNumbers = new Map(academicGroups.map((group, index) => [group, index + 1]))
  const verificationText = r => r.modo_comprobacion === 'entidad_oferente'
    ? 'Verificación externa por la entidad oferente. BecaNexo no acredita este requisito.'
    : 'Condición sobre datos declarados. No constituye una verificación documental.'
  return records.length ? <div className="requirement-group">{sharedVerification && <p className="requirement-group-note accent-note">Para todos los requisitos de este grupo: {verificationText(records[0])}</p>}{academicGroups.length > 0 && <p className="requirement-group-note">Los requisitos con el mismo grupo académico deben cumplirse con una misma formación.</p>}<ul className="detail-list">{records.map((r) => {
    const type = catalogs.tipos_requisito.find((t) => t.id === r.tipo_requisito)
    const original = r.texto_original?.trim() || ''
    const values = Object.entries(r.valor_estructurado || {}).filter(([key, value]) =>
      !(key === 'descripcion' && String(value).trim() === original))
    const externalLabel = type?.codigo === 'OTRO' && /econ[oó]mic|socioecon[oó]mic/iu.test(original)
      ? 'Condición socioeconómica' : type?.codigo === 'OTRO' && /bachiller|t[ií]tulo de tercer nivel/iu.test(original)
        ? 'Condición de formación previa' : type?.nombre || 'Requisito'
    return <li key={r.id} className="requirement-item"><Heading>{externalLabel} <span className="requirement-kind">{r.obligatorio ? 'Obligatorio' : 'Preferencia'}</span>{r.grupo_formacion && <span className="requirement-group-label">Grupo académico {groupNumbers.get(r.grupo_formacion)}</span>}</Heading><p className="preserve-text">{r.texto_original}</p>
      {values.length > 0 && <dl className="detail-data requirement-values">{values.map(([key, value]) => <div key={key}><dt>{fieldLabel(type, key) || key}</dt><dd>{ruleText(value, type?.esquema_valor?.campos?.[key], catalogs)}</dd></div>)}</dl>}
      {r.fecha_referencia && <p>Fecha de referencia: {r.fecha_referencia}</p>}
      {r.destino && <p>Condición del destino: {catalogs.paises.find(p => p.id === r.destino)?.nombre || 'No especificado'}</p>}
      {r.documento_exigido && <p>Documento exigido: {r.documento_exigido}</p>}{r.detalle_acreditacion && <p>Condiciones documentales: {r.detalle_acreditacion}</p>}
      {!sharedVerification && <p className="accent-note">{verificationText(r)}</p>}
      {r.referencia_bases && <details className="detail-reference"><summary>Referencia y evidencia en las bases</summary><p className="preserve-text">{r.referencia_bases}</p></details>}
    </li>
  })}</ul></div> : <p>No especificado. La ausencia de información no significa que no existan requisitos.</p>
}

const isDocument = (r, catalogs) => ['DOCUMENTO', 'ACREDITACION'].includes(catalogs.tipos_requisito.find(t => t.id === r.tipo_requisito)?.codigo)
function documentLink(value) {
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? value : null } catch { return null }
}

export function Documentation({ offer, catalogs, scopeId, showWarning = true }) {
  const documents = offer.requisitos.filter(r => isDocument(r, catalogs) && (scopeId === undefined || (r.opcion_estudio ?? null) === scopeId))
  const groups = [{ id: null, title: 'Documentos comunes a la convocatoria' }, ...offer.opciones.map(o => ({ id: o.id, title: `Documentos de la opción: ${o.programa || `${o.nivel} / ${o.modalidad}`} (#${o.id})` }))]
    .filter(group => scopeId === undefined || group.id === scopeId)
  const scoped = scopeId !== undefined
  const nested = scoped && scopeId !== null
  return <section className={nested ? 'offer-documents-scoped' : 'profile-card offer-detail-section offer-documents-common'} aria-label={nested ? 'Documentación de este ámbito' : undefined}>
    {nested ? <h3>Documentación requerida</h3> : <h2>Documentación requerida</h2>}
    {showWarning && <p>Los documentos se presentan ante la entidad oferente. BecaNexo no los recibe ni acredita; su verificación externa permanece pendiente.</p>}
    {!documents.length && <p>{scoped ? 'No se registraron documentos para este ámbito. Consulta las bases oficiales.' : 'Consulta las bases oficiales para confirmar la documentación requerida'}</p>}
    {groups.map(group => {
      const rows = documents.filter(r => (r.opcion_estudio ?? null) === group.id)
      return rows.length ? <div key={group.id ?? 'common'}>{nested ? <h4>{group.title}</h4> : <h3>{group.title}</h3>}<ul className="detail-list">{rows.map(r => {
        const v = r.valor_estructurado || {}
        const type = catalogs.tipos_requisito.find(t => t.id === r.tipo_requisito)
        const title = v.documento || v.certificados_admitidos || r.documento_exigido || 'Documento indicado en las bases'
        const seen = new Set([String(title).trim()])
        const facts = []
        const add = (label, value) => {
          if (value == null || String(value).trim() === '' || seen.has(String(value).trim())) return
          seen.add(String(value).trim()); facts.push({ label, value: String(value) })
        }
        add('Condición publicada', r.texto_original)
        add('Condiciones o alternativas', v.condiciones)
        add('Condiciones de acreditación', r.detalle_acreditacion)
        add('Documento complementario', r.documento_exigido)
        add('Certificados admitidos', v.certificados_admitidos)
        add('Vigencia publicada', v.vigencia)
        const extra = Object.entries(v).filter(([key]) => !['documento', 'certificados_admitidos', 'condiciones', 'vigencia', 'url_documento'].includes(key))
        return <li key={r.id} className="document-item"><h4 className="preserve-text">{title}</h4><p className="requirement-kind">{r.obligatorio ? 'Documento exigido según las bases' : 'No obligatorio según lo registrado'}</p>
          {facts.length > 0 && <dl className="document-facts">{facts.map(({ label, value }) => <div key={label}><dt>{label}</dt><dd className="preserve-text">{value}</dd></div>)}</dl>}
          {extra.length > 0 && <dl className="document-facts">{extra.map(([key, value]) => <div key={key}><dt>{fieldLabel(type, key) || key}</dt><dd className="preserve-text">{value !== null && typeof value === 'object' ? JSON.stringify(value) : ruleText(value, type?.esquema_valor?.campos?.[key], catalogs)}</dd></div>)}</dl>}
          {r.fecha_referencia && <p>Fecha de referencia: {r.fecha_referencia}</p>}
          {r.destino && <p>Aplicable al destino: {catalogs.paises.find(p => p.id === r.destino)?.nombre || 'Consultar las bases'}</p>}
          {r.modo_comprobacion && r.modo_comprobacion !== 'entidad_oferente' && <p>Modo de comprobación registrado: {r.modo_comprobacion}</p>}
          {r.referencia_bases && <details className="detail-reference"><summary>Referencia y evidencia en las bases</summary><p className="preserve-text">{r.referencia_bases}</p></details>}
        </li>
      })}</ul></div> : null
    })}
  </section>
}

function officialDocuments(offer, officialUrl, catalogs) {
  if (offer.titulo?.endsWith('(Ficticia)')) return []
  const links = []
  const seen = new Set(officialUrl ? [officialUrl] : [])
  const add = (url, name, type) => {
    const safe = documentLink(url)
    if (!safe || seen.has(safe)) return
    seen.add(safe)
    links.push({ url: safe, name, type })
  }
  add(offer.url_bases, 'Bases o reglamento enlazado', 'Referencia de bases registrada')
  for (const requirement of offer.requisitos || []) {
    if (!isDocument(requirement, catalogs)) continue
    const values = requirement.valor_estructurado || {}
    add(values.url_documento, values.documento || values.certificados_admitidos || requirement.documento_exigido || 'Documento oficial',
      'Documento o formulario indicado en los requisitos')
  }
  return links
}

function OptionStudy({ option, index, offer, catalogs }) {
  const benefits = offer.beneficios.filter(b => b.opcion_estudio === option.id)
  const requirements = offer.requisitos.filter(r => r.opcion_estudio === option.id && !isDocument(r, catalogs))
  const documents = offer.requisitos.filter(r => r.opcion_estudio === option.id && isDocument(r, catalogs))
  const countries = (option.paises || []).map(id => catalogs.paises.find(p => p.id === id)?.nombre || String(id))
  return <article className="profile-card offer-option" aria-label={`Opción ${index + 1}: ${option.programa || 'Programa no especificado'}`}>
    <div className="offer-option-heading"><span className="offer-option-number">Opción {index + 1}</span><h3>{option.programa || 'Programa no especificado'}</h3><p>{readable(option.nivel)} · {readable(option.modalidad)}</p></div>
    <dl className="offer-option-facts"><div><dt>País de estudio</dt><dd>{countries.join(', ') || 'No especificado'}</dd></div>
      {option.institucion_destino && <div><dt>Institución de destino</dt><dd>{option.institucion_destino}</dd></div>}
      {option.inicio_estudios && <div><dt>Inicio de estudios</dt><dd>{dayDate(option.inicio_estudios)}</dd></div>}
      {option.duracion_meses != null && <div><dt>Duración</dt><dd>{option.duracion_meses} meses</dd></div>}
      {option.cupos != null && <div><dt>Cupos</dt><dd>{option.cupos}</dd></div>}</dl>
    <div className="offer-option-disclosures">
      {!benefits.length && !requirements.length && !documents.length && <p className="small-note">Esta opción comparte los requisitos, beneficios y documentos generales de la convocatoria. No se han registrado condiciones adicionales específicas.</p>}
      {benefits.length > 0 && <details className="offer-disclosure"><summary>Beneficios específicos de esta opción <span>{benefits.length}</span></summary><BenefitList records={benefits} nested /></details>}
      {requirements.length > 0 && <details className="offer-disclosure" open><summary>Requisitos académicos y personales <span>{requirements.length}</span></summary><RequirementList records={requirements} catalogs={catalogs} nested /></details>}
      {documents.length > 0 && <details className="offer-disclosure"><summary>Referencias, documentos y verificación <span>{documents.length}</span></summary><Documentation offer={offer} catalogs={catalogs} scopeId={option.id} showWarning={false} /></details>}
    </div>
  </article>
}

export default function OfferDetail() {
  const { id } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get(`becas/${id}`), offersApi.get('becas/catalogos')]).then(([offer, catalogs]) => { if (live) { setData({ offer, catalogs }); setError('') } })
      .catch((e) => { if (live) setError(e.status === 404 ? 'Esta convocatoria no está disponible para consulta.' : e.message) })
    return () => { live = false }
  }, [id, retry])
  const offer = String(data?.offer.id) === id ? data.offer : null
  const options = offer?.opciones || []
  const academicAreas = offer ? (offer.areas || []).map(id => data.catalogs.areas?.find(area => area.id === id)?.nombre).filter(Boolean) : []
  const destinations = offer ? unique(options.flatMap(option => (option.paises || []).map(countryId => data.catalogs.paises.find(country => country.id === countryId)?.nombre))) : []
  const financing = offer ? benefitSummary(offer.beneficios) : []
  const period = offer ? publishedPeriod(offer) : null
  const officialUrl = offer ? documentLink(offer.url_oficial) : null
  const demonstration = offer?.titulo?.endsWith('(Ficticia)')
  const documents = offer ? officialDocuments(offer, officialUrl, data.catalogs) : []
  return <OffersLayout><Link className="back-link" to="/becas"><Icon name="back" /><span>Volver al catálogo</span></Link>
    {error && <><Message>{error}</Message><Button icon="refresh" onClick={() => setRetry(retry + 1)}>Reintentar</Button></>}
    {!data && !error && <p role="status"><Icon name="loading" />Cargando convocatoria…</p>}
    {offer && <><header className="offer-detail-hero"><div className="offer-hero-top"><div className="offer-detail-heading"><span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span><h1>{offer.titulo}</h1><p className="offer-provider">{providerLabel(offer, { detailed: true })}</p></div>
      <div className="offer-hero-actions">{demonstration ? <><Link className="button offer-official-link" to={`/becas/${offer.id}/postulacion-demo`}><Icon name="external" /><span>Ir a postulación (demostración)</span></Link><p className="small-note">Convocatoria ficticia para demostración; no admite postulaciones.</p></> : officialUrl ? <a className="button offer-official-link" href={officialUrl} target="_blank" rel="noopener noreferrer"><Icon name="external" /><span>Ver convocatoria oficial</span></a> : <p className="small-note">El enlace oficial no está disponible. Consulta la información publicada antes de continuar.</p>}
        <FavoriteButton key={`${offer.id}-${offer.favorito_id}`} offerId={offer.id} initialId={offer.favorito_id} /></div></div>
      <dl className="offer-hero-facts"><div><dt>Cierre</dt><dd>{closingText(offer)}</dd></div>
        {options.length > 0 && <><div><dt>{options.length === 1 ? 'Nivel y modalidad' : 'Niveles y modalidades'}</dt><dd>{unique(options.map(o => readable(o.nivel))).join(', ')} · {unique(options.map(o => readable(o.modalidad))).join(', ')}</dd></div>
          <div><dt>{destinations.length === 1 ? 'Destino' : 'Destinos'}</dt><dd>{destinations.join(', ') || 'No especificado'}</dd></div></>}
        {financing.length > 0 && <div className="offer-hero-financing"><dt>Financiamiento</dt><dd>{financing.map((line, index) => <span key={index}>{line}</span>)}</dd></div>}</dl>
      {!demonstration && officialUrl && <p className="small-note">El enlace oficial permite consultar la convocatoria; no necesariamente abre un formulario de postulación.</p>}</header>
      {offer.estado === 'cerrada' && <Message kind="info">La fecha de cierre ya pasó. Esta oferta se conserva para consulta.</Message>}
      {offer.estado === 'sin_fecha' && <Message kind="info">La vigencia está por verificar. Esta beca se conserva para consulta y no se recomienda como postulable.</Message>}
      {offer.estado === 'cierre_hoy' && <Message kind="info">El cierre está indicado solo por día. No se conoce la hora; consulta el sitio oficial antes de postular.</Message>}
      <section className="profile-card offer-detail-section"><h2>Resumen y condiciones generales</h2><p className="preserve-text">{offer.descripcion}</p>
        <dl className="detail-data"><div><dt>Tipo de beca</dt><dd>{display(offer.tipo_beca_nombre)}</dd></div><div><dt>Áreas académicas</dt><dd>{academicAreas.length ? academicAreas.join(', ') : 'No especificadas en esta ficha; consulta la fuente oficial'}</dd></div><div><dt>Cobertura publicada</dt><dd>{financing.length ? financing.join(' · ') : display(offer.cobertura_tipo)}</dd></div>
          {period ? <div><dt>Período de postulación</dt><dd>Apertura: {dayDate(period.start)} · Cierre: {dayDate(period.end)} · Horas no informadas</dd></div>
            : <><div><dt>Apertura</dt><dd>{date(offer.apertura)}</dd></div>{offer.cierre_original && <div><dt>Fecha según fuente</dt><dd>{offer.cierre_original}</dd></div>}</>}
          <div><dt>Publicación en la fuente</dt><dd>{display(offer.fecha_publicacion)}</dd></div><div><dt>Gastos no cubiertos</dt><dd>{display(offer.gastos_no_cubiertos)}</dd></div><div><dt>Obligaciones</dt><dd>{display(offer.obligaciones_beneficiario)}</dd></div></dl><p className="small-note">Los instantes se muestran en America/Guayaquil. Un cierre expresado solo como día no tiene hora confirmada.</p></section>
      <section className="profile-card offer-detail-section"><h2>Alcance académico</h2>
        <dl className="detail-data"><div><dt>Estado del alcance</dt><dd>{offer.alcance_academico === 'programas' ? 'Programas específicos documentados' : offer.alcance_academico === 'transversal' ? 'Transversal institucional documentado' : 'Pendiente de confirmar'}</dd></div>
          {offer.alcance_detalle && <div><dt>Alcance según la fuente</dt><dd className="preserve-text">{offer.alcance_detalle}</dd></div>}
          {offer.alcance_exclusiones && <div><dt>Carreras excluidas</dt><dd className="preserve-text">{offer.alcance_exclusiones}</dd></div>}
          {offer.alcance_sede && <div><dt>Sede</dt><dd className="preserve-text">{offer.alcance_sede}</dd></div>}
          {offer.alcance_periodo && <div><dt>Período académico</dt><dd className="preserve-text">{offer.alcance_periodo}</dd></div>}</dl>
        <p className="small-note">Las opciones de estudio registradas pueden ser parciales. El alcance documental no confirma por sí solo la elegibilidad; consulta las condiciones oficiales.</p></section>
      <Comparison key={offer.id} offerId={offer.id} catalogs={data.catalogs} />
      <h2 className="section-heading offer-options-heading">Opciones de estudio</h2><p className="small-note offer-options-note">Los requisitos, beneficios y documentos generales se aplican a todas las opciones salvo que se indique una condición específica. La entidad oferente verifica los documentos y certificados; BecaNexo no los recibe.</p>{offer.opciones.map((o, index) => <OptionStudy key={o.id} option={o} index={index} offer={offer} catalogs={data.catalogs} />)}
      <section className="profile-card offer-detail-section"><h2>Beneficios comunes</h2><BenefitList records={offer.beneficios.filter((b) => !b.opcion_estudio)} /><p className="profile-note">Cada porcentaje corresponde exclusivamente al concepto financiado. No representa el costo total de estudiar.</p></section>
      <section className="profile-card offer-detail-section"><h2>Requisitos comunes</h2><RequirementList records={offer.requisitos.filter((r) => !r.opcion_estudio && !isDocument(r, data.catalogs))} catalogs={data.catalogs} /></section>
      <Documentation offer={offer} catalogs={data.catalogs} scopeId={null} showWarning={false} />
      <section className="profile-card offer-source offer-detail-section"><h2>{demonstration ? 'Datos de demostración' : 'Bases y documentos oficiales'}</h2>{demonstration ? <p>Esta convocatoria es ficticia. No existen bases ni postulación reales.</p> : <><p>La postulación se realiza fuera de BecaNexo. La entidad oferente confirma los documentos y adjudica la beca.</p>
        {documents.length ? <ul className="official-document-list">{documents.map(document => <li key={document.url}><Icon name="document" /><div><strong className="preserve-text">{document.name}</strong><span>{document.type} · Fuente: {offer.institucion?.nombre || 'publicación oficial'}</span></div><a className="secondary-link" href={document.url} target="_blank" rel="noopener noreferrer"><Icon name="external" /><span>Ver documento</span></a></li>)}</ul> : <p className="small-note">No hay archivos oficiales enlazados en este registro. Consulta la información publicada por la entidad.</p>}
        {officialUrl && !documents.length && <a className="secondary-link" href={officialUrl} target="_blank" rel="noopener noreferrer"><Icon name="external" /><span>Consultar información oficial</span></a>}</>}
        {offer.actualizado_en && <p className="small-note">Última actualización: {date(offer.actualizado_en)}</p>}</section>
      <SimilarOffers key={offer.id} offerId={offer.id} /></>}
  </OffersLayout>
}
