import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { offersApi, ApiError } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import OfferForm from '../components/OfferForm'
import ConfirmDelete from '../components/ConfirmDelete'
import Message from '../components/Message'
import Button from '../components/Button'
import { generalFields, optionFields, benefitFields, requirementFields, optionLabel } from './offerFields'
import { stateLabel } from './offerDisplay'
import OriginPanel from '../components/OriginPanel'

async function allInstitutions() {
  const rows = []
  for (let page = 1; ; page += 1) {
    const result = await offersApi.get('gestion/instituciones', { page_size: 50, page })
    rows.push(...result.results)
    if (rows.length >= result.count) return rows
  }
}

function safeEvidenceUrl(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password &&
      !url.hash && (!url.search || /^\?t=\d+$/.test(url.search))
  } catch { return false }
}

function initialWithEvidence(offer, catalogs, origin) {
  const initial = { ...offer, institucion: offer.institucion?.id ?? null }
  const fields = origin?.automatico ? origin.candidatos_editables?.otros_campos : null
  if (!fields) return initial
  if (!initial.cobertura_tipo && ['total', 'parcial', 'mixta'].includes(fields.cobertura_tipo_sugerida))
    initial.cobertura_tipo = fields.cobertura_tipo_sugerida
  if (!initial.gastos_no_cubiertos && fields.gastos_no_cubiertos_literal)
    initial.gastos_no_cubiertos = fields.gastos_no_cubiertos_literal
  const bases = origin.enlaces_origen?.bases || []
  if (!initial.url_bases && bases.length === 1 && safeEvidenceUrl(bases[0].url))
    initial.url_bases = bases[0].url
  const type = catalogs.tipos_beca.find((row) => row.nombre.toLocaleLowerCase('es') === fields.tipo_beca_literal?.toLocaleLowerCase('es'))
  if (!initial.tipo_beca && type) initial.tipo_beca = type.id
  if (!initial.fecha_publicacion && /^\d{4}-\d{2}-\d{2}$/.test(fields.fechas?.publicacion || ''))
    initial.fecha_publicacion = fields.fechas.publicacion
  const areaNames = fields.areas_literales
  if ((!initial.areas || initial.areas.length === 0) && Array.isArray(areaNames) && areaNames.length > 0 &&
      areaNames.every((name) => typeof name === 'string')) {
    const matches = areaNames.map((name) => catalogs.areas.find((area) => area.nombre.toLocaleLowerCase('es') === name.toLocaleLowerCase('es')))
    if (matches.every(Boolean) && new Set(matches.map((area) => area.id)).size === matches.length)
      initial.areas = matches.map((area) => area.id)
  }
  return initial
}

function Records({ name, title, offer, catalogs, onSaved, suggestion }) {
  const [editing, setEditing] = useState(() => suggestion?.name === name
    ? name === 'requisitos' ? { texto_original: suggestion.value.texto_original, validado: false,
        valor_estructurado: suggestion.value.estado === 'identificada' ? suggestion.value.valor_sugerido : {} }
      : name === 'beneficios' ? { concepto: suggestion.value.concepto_sugerido || '',
        porcentaje: suggestion.value.porcentaje, monto: suggestion.value.monto,
        moneda: suggestion.value.moneda || '', tope_original: suggestion.value.tope_original || '',
        tope_monto: suggestion.value.tope_monto, tope_moneda: suggestion.value.tope_moneda || '',
        detalle: suggestion.value.texto_original }
        : { nivel: suggestion.value.nivel, modalidad: suggestion.value.modalidad } : null)
  const [deleting, setDeleting] = useState(null)
  const [typeId, setTypeId] = useState(() => suggestion?.name === 'requisitos' && name === 'requisitos'
    ? String(catalogs.tipos_requisito.find((row) => row.codigo === suggestion.value.tipo_sugerido)?.id
      || catalogs.tipos_requisito.find((row) => row.codigo === 'OTRO')?.id || '') : '')
  const records = offer[name]
  const type = catalogs.tipos_requisito.find((t) => t.id === Number(typeId))
  const fields = name === 'opciones' ? optionFields(catalogs) : name === 'beneficios' ? benefitFields(offer.opciones, catalogs.paises) : type ? requirementFields(type, catalogs, offer.opciones) : []
  const initial = editing ? { activa: true, activo: true, obligatorio: true, validado: false, relacion_formacion: 'pendiente', ...editing,
    ...Object.fromEntries(Object.entries(editing.valor_estructurado || {}).map(([key, value]) => [`regla_${key}`, value])) } : {}
  async function save(values) {
    let data = values
    if (name === 'requisitos') {
      const value = Object.fromEntries(Object.entries(values).filter(([key, v]) => key.startsWith('regla_') && v != null && (!Array.isArray(v) || v.length)).map(([key, v]) => [key.slice(6), v]))
      data = { ...Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith('regla_'))), tipo_requisito: type.id, valor_estructurado: value,
        modo_comprobacion: ['ACREDITACION', 'DOCUMENTO', 'OTRO'].includes(type.codigo) ? 'entidad_oferente' : 'dato_declarado' }
    }
    try {
      const response = await offersApi.write(`gestion/convocatorias/${offer.id}/${name}${editing.id ? `/${editing.id}` : ''}`, editing.id ? 'PATCH' : 'POST', data)
      onSaved(name, response); setEditing(null)
    } catch (e) {
      if (e.fields?.valor_estructurado && typeof e.fields.valor_estructurado === 'object' && !Array.isArray(e.fields.valor_estructurado)) {
        throw new ApiError(e.message, e.status, { ...e.fields, ...Object.fromEntries(Object.entries(e.fields.valor_estructurado).map(([k, v]) => [`regla_${k}`, v])) })
      }
      if (e.fields?.valor_estructurado) throw new ApiError(String(e.fields.valor_estructurado), e.status, e.fields)
      throw e
    }
  }
  return <section className="profile-card" aria-label={title}><h2>{title}</h2>
    {name === 'requisitos' && <p className="profile-note">Revisar la transcripción no verifica documentos de postulantes. Los certificados los comprueba la entidad oferente.</p>}
    <ul className="record-list offer-records">{records.map((r) => <li key={r.id}><span>{name === 'opciones' ? `${optionLabel(r, catalogs.paises, records)}${r.activa ? '' : ' · Inactiva'}` : name === 'beneficios' ? r.concepto : `${catalogs.tipos_requisito.find((t) => t.id === r.tipo_requisito)?.nombre}: ${r.texto_original}${r.activo ? '' : ' · Inactivo'}`}</span>
      <div className="record-actions"><button className="text-button" disabled={editing !== null} onClick={() => { setEditing(r); setTypeId(String(r.tipo_requisito || '')) }}><Icon name="edit" /><span>Editar</span></button>
        {name === 'beneficios' && <button className="text-button danger-text" disabled={editing !== null} onClick={() => setDeleting(r)}><Icon name="delete" /><span>Eliminar</span></button>}</div></li>)}</ul>
    {!records.length && <p className="empty-note">Todavía no hay registros. Lo no informado se conserva como desconocido.</p>}
    {!editing ? <Button icon="add" className="button-light" onClick={() => { setEditing({}); setTypeId('') }}>Añadir {title.toLowerCase()}</Button> : <div className="record-editor"><h3>{editing.id ? 'Editar registro' : 'Nuevo registro'}</h3>
      {name === 'requisitos' && <div className="field"><label htmlFor="requirement-type">Tipo de requisito</label><select id="requirement-type" value={typeId} onChange={(e) => setTypeId(e.target.value)}><option value="">Selecciona un tipo</option>{catalogs.tipos_requisito.map((t) => <option key={t.id} value={t.id}>{t.nombre}</option>)}</select></div>}
      {fields.length > 0 ? <OfferForm key={`${editing.id || 'new'}-${typeId}`} fields={fields} initial={initial} label={`Guardar ${title.toLowerCase()}`} onSubmit={save} onCancel={() => setEditing(null)} /> : <Button icon="cancel" onClick={() => setEditing(null)}>Cancelar</Button>}
    </div>}
    {deleting && <ConfirmDelete title="este beneficio" description="Se quitará de la convocatoria y se conservará su instantánea en la auditoría. La convocatoria volverá a revisión pendiente." onCancel={() => setDeleting(null)} onConfirm={async () => {
      await offersApi.write(`gestion/convocatorias/${offer.id}/beneficios/${deleting.id}`, 'DELETE'); onSaved(name, null, deleting.id); setDeleting(null)
    }} />}
  </section>
}

export default function OfferEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [loaded, setLoaded] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)
  const [suggestion, setSuggestion] = useState(null)
  useEffect(() => {
    let live = true
    Promise.all([offersApi.get('becas/catalogos'), allInstitutions(), id ? offersApi.get(`gestion/convocatorias/${id}`) : Promise.resolve(null),
      id ? offersApi.get(`gestion/rastreo/convocatorias/${id}/origen`).catch(() => null) : Promise.resolve(null)])
      .then(([catalogs, institutions, offer, origin]) => { if (live) { setLoaded({ catalogs, institutions, offer, origin }); setError('') } }).catch((e) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [id, retry])
  async function action(name) {
    setBusy(true); setError(''); setNotice('')
    try { const offer = await offersApi.write(`gestion/convocatorias/${id}/${name}`, 'POST'); setLoaded((old) => ({ ...old, offer })); setNotice(name === 'publicar' ? 'Convocatoria publicada.' : 'Convocatoria pausada.') }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  function childSaved(name, row, deletedId) {
    setNotice('Registro guardado. Revisa y publica nuevamente para mostrar los cambios.'); setLoaded((old) => ({ ...old, offer: { ...old.offer, version: old.offer.version + 1, revision: 'pendiente', estado: old.offer.activa ? 'borrador' : 'pausada',
      [name]: deletedId ? old.offer[name].filter((r) => r.id !== deletedId) : old.offer[name].some((r) => r.id === row.id) ? old.offer[name].map((r) => r.id === row.id ? row : r) : [...old.offer[name], row] } }))
  }
  return <OffersLayout><Link className="back-link" to="/gestion/convocatorias"><Icon name="back" /><span>Convocatorias</span></Link><h1>{id ? 'Editar y revisar convocatoria' : 'Crear convocatoria'}</h1><p>Comprueba la información contra las bases oficiales. No verifica documentos de estudiantes.</p>
    <Message>{error}</Message>{!loaded && (error ? <Button icon="refresh" onClick={() => setRetry(retry + 1)}>Reintentar</Button> : <p role="status"><Icon name="loading" />Cargando editor…</p>)}<Message kind="success">{notice}</Message>
    {loaded && <><section className="profile-card"><h2>01 · Identificación, fechas y condiciones</h2>{loaded.offer && <p className="profile-note">Revisión: {loaded.offer.revision} · Estado: {stateLabel(loaded.offer.estado)}. Editar retira la publicación hasta una nueva revisión.</p>}
      {!loaded.offer && <p>Guarda el borrador antes de añadir opciones.</p>}
      <OfferForm key={id || 'new'} fields={generalFields(loaded.catalogs, loaded.institutions).map(field => field.name === 'institucion' ? { ...field, required: !loaded.offer?.origen_automatico, hint: <Link className="offer-institution-link" to="/gestion/instituciones"><Icon name="institutions" /><span>Gestionar entidades oferentes</span></Link> } : field)} initial={loaded.offer ? initialWithEvidence(loaded.offer, loaded.catalogs, loaded.origin) : { alcance_academico: 'pendiente' }} proposal={suggestion?.name === 'general' ? suggestion.value : null} label="Guardar convocatoria" onSubmit={async (values) => {
        const offer = await offersApi.write(id ? `gestion/convocatorias/${id}` : 'gestion/convocatorias', id ? 'PATCH' : 'POST', values)
        if (!id) navigate(`/gestion/convocatorias/${offer.id}`)
        else { setLoaded((old) => ({ ...old, offer })); setNotice('Cambios guardados. Publica de nuevo después de revisar.') }
      }} /></section>
      {loaded.offer && <><OriginPanel offer={loaded.offer} onPrepare={(name, value) => {
        if (loaded.offer.revision === 'validada') { setNotice('La convocatoria ya está validada; revisa su versión antes de incorporar evidencia nueva.'); return }
        if (name === 'general' && loaded.offer[value.campo]) { setNotice('Este campo ya tiene información; conserva la edición administrativa existente.'); return }
        if (name === 'requisitos' && loaded.offer.requisitos.some((row) => row.texto_original === value.texto_original)) { setNotice('Este requisito ya existe en el borrador.'); return }
        if (name === 'beneficios' && loaded.offer.beneficios.some((row) => row.concepto === value.concepto_sugerido)) { setNotice('Este beneficio ya existe en el borrador.'); return }
        setSuggestion({ name, value, id: crypto.randomUUID() }); setNotice('Propuesta preparada. Revisa su contexto y guarda solo si corresponde.')
      }} /><Records key={`opciones:${suggestion?.name === 'opciones' ? suggestion.id : 'base'}`} name="opciones" title="Opciones de estudio" offer={loaded.offer} catalogs={loaded.catalogs} onSaved={childSaved} suggestion={suggestion} /><Records key={`beneficios:${suggestion?.name === 'beneficios' ? suggestion.id : 'base'}`} name="beneficios" title="Beneficios" offer={loaded.offer} catalogs={loaded.catalogs} onSaved={childSaved} suggestion={suggestion} /><Records key={`requisitos:${suggestion?.name === 'requisitos' ? suggestion.id : 'base'}`} name="requisitos" title="Requisitos" offer={loaded.offer} catalogs={loaded.catalogs} onSaved={childSaved} suggestion={suggestion} />
        <section className="profile-card"><h2>Revisión y publicación</h2><p className="profile-note">Al publicar confirmas la entidad ecuatoriana y la transcripción de las bases. Se exige una opción activa, descripción y enlace oficial; todos los requisitos activos deben estar revisados. Guarda cada sección antes de publicar.</p>
          <div className="form-actions"><Button icon="publish" busy={busy} onClick={() => action('publicar')}>Validar y publicar</Button>{loaded.offer.revision === 'validada' && loaded.offer.activa && <><Button icon="pause" disabled={busy} className="button-light" onClick={() => action('pausar')}>Pausar convocatoria</Button><Link to={`/becas/${id}`}>Ver en el catálogo</Link></>}</div></section></>}
    </>}
  </OffersLayout>
}
