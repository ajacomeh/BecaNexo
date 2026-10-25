import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Message from '../components/Message'
import Button from '../components/Button'
import { display, date, stateLabel } from './offerDisplay'

export function BenefitList({ records }) {
  return records.length ? <ul className="detail-list">{records.map((b) => <li key={b.id}><h3>{b.concepto}</h3>
    <p>{b.porcentaje != null ? `${b.porcentaje} % de ${b.concepto}` : 'Porcentaje no especificado'} · {b.monto != null ? `${b.monto} ${b.moneda}` : 'Monto no especificado'}</p>
    <p>Periodicidad: {display(b.periodicidad)}</p><p>{display(b.detalle)}</p></li>)}</ul> : <p>No especificado</p>
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

export function RequirementList({ records, catalogs }) {
  return records.length ? <ul className="detail-list">{records.map((r) => {
    const type = catalogs.tipos_requisito.find((t) => t.id === r.tipo_requisito)
    return <li key={r.id}><h3>{type?.nombre || 'Requisito'} <span className="small-note">· {r.obligatorio ? 'Obligatorio' : 'Preferencia'}</span></h3><p className="preserve-text">{r.texto_original}</p>
      <dl className="detail-data">{Object.entries(r.valor_estructurado || {}).map(([key, value]) => <div key={key}><dt>{type?.esquema_valor.campos[key]?.label || key}</dt><dd>{ruleText(value, type?.esquema_valor.campos[key], catalogs)}</dd></div>)}</dl>
      <p>Fecha de referencia: {display(r.fecha_referencia)}</p><p>Referencia en las bases: {display(r.referencia_bases)}</p>
      <p>Documento exigido: {display(r.documento_exigido)}</p><p>Condiciones documentales: {display(r.detalle_acreditacion)}</p>
      <p className="accent-note">{r.modo_comprobacion === 'entidad_oferente' ? 'Verificación externa por la entidad oferente. BecaNexo no acredita este requisito.' : 'Condición sobre datos declarados. No constituye una verificación documental.'}</p>
    </li>
  })}</ul> : <p>No especificado. La ausencia de información no significa que no existan requisitos.</p>
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
  return <OffersLayout><Link className="back-link" to="/becas">← Volver al catálogo</Link>
    {error && <><Message>{error}</Message><Button onClick={() => setRetry(retry + 1)}>Reintentar</Button></>}
    {!data && !error && <p role="status">Cargando convocatoria…</p>}
    {offer && <><div className="page-heading"><div><span className={`status-pill state-${offer.estado}`}>{stateLabel(offer.estado)}</span><h1>{offer.titulo}</h1><p>{offer.institucion.nombre} · Entidad oferente ecuatoriana</p></div></div>
      {offer.estado === 'cerrada' && <Message kind="info">La fecha de cierre ya pasó. Esta oferta se conserva para consulta.</Message>}
      <section className="profile-card"><h2>Descripción y condiciones generales</h2><p className="preserve-text">{offer.descripcion}</p>
        <dl className="detail-data"><div><dt>Tipo de beca</dt><dd>{display(offer.tipo_beca_nombre)}</dd></div><div><dt>Cobertura publicada</dt><dd>{display(offer.cobertura_tipo)}</dd></div>
          <div><dt>Apertura</dt><dd>{date(offer.apertura)}</dd></div><div><dt>Cierre</dt><dd>{date(offer.cierre)}</dd></div><div><dt>Cierre según fuente</dt><dd>{display(offer.cierre_original)}</dd></div>
          <div><dt>Publicación en la fuente</dt><dd>{display(offer.fecha_publicacion)}</dd></div><div><dt>Gastos no cubiertos</dt><dd>{display(offer.gastos_no_cubiertos)}</dd></div><div><dt>Obligaciones</dt><dd>{display(offer.obligaciones_beneficiario)}</dd></div></dl><p className="small-note">Fechas y horas en America/Guayaquil.</p></section>
      <section className="profile-card"><h2>Beneficios comunes</h2><BenefitList records={offer.beneficios.filter((b) => !b.opcion_estudio)} /><p className="profile-note">Cada porcentaje corresponde exclusivamente al concepto financiado. No representa el costo total de estudiar.</p></section>
      <section className="profile-card"><h2>Requisitos comunes</h2><RequirementList records={offer.requisitos.filter((r) => !r.opcion_estudio)} catalogs={data.catalogs} /></section>
      <h2 className="section-heading">Opciones de estudio</h2>{offer.opciones.map((o) => <section className="profile-card" key={o.id}><h2>{o.programa || 'Programa no especificado'}</h2><p className="accent-note">{o.nivel} · {o.modalidad}</p>
        <dl className="detail-data"><div><dt>Países de estudio</dt><dd>{o.paises.map((p) => data.catalogs.paises.find((x) => x.id === p)?.nombre).join(', ') || 'No especificado'}</dd></div>
          <div><dt>Institución de destino</dt><dd>{display(o.institucion_destino)}</dd></div><div><dt>Inicio</dt><dd>{display(o.inicio_estudios)}</dd></div><div><dt>Duración (meses)</dt><dd>{display(o.duracion_meses)}</dd></div><div><dt>Cupos</dt><dd>{display(o.cupos)}</dd></div></dl>
        <h3>Beneficios de esta opción</h3><BenefitList records={offer.beneficios.filter((b) => b.opcion_estudio === o.id)} /><h3>Requisitos de esta opción</h3><RequirementList records={offer.requisitos.filter((r) => r.opcion_estudio === o.id)} catalogs={data.catalogs} /></section>)}
      <section className="profile-card"><h2>Fuente oficial y postulación externa</h2><p>BecaNexo no recibe documentos ni tramita postulaciones. La entidad oferente verifica certificados y decide la adjudicación.</p>
        <div className="form-actions"><a className="secondary-link" href={offer.url_oficial} target="_blank" rel="noopener noreferrer">Consultar fuente oficial</a>{offer.url_bases && <a href={offer.url_bases} target="_blank" rel="noopener noreferrer">Consultar bases</a>}</div><p className="small-note">Última actualización: {date(offer.actualizado_en)}</p></section></>}
  </OffersLayout>
}
