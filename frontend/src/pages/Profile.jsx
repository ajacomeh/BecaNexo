import Icon from '../components/Icon'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { profileApi, ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import ProfileLayout from '../components/ProfileLayout'
import ProfileForm from '../components/ProfileForm'
import ProfileRecords from '../components/ProfileRecords'
import Button from '../components/Button'
import Message from '../components/Message'
import { profileFields } from './profileFields'

export default function Profile({ preferences = false }) {
  const location = useLocation()
  const { user, updateName } = useAuth()
  const [state, setState] = useState({ loading: true, data: null, error: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    const resources = preferences ? ['idiomas', 'preferencias', 'areas', 'destinos'] : ['formaciones', 'experiencias']
    Promise.all([profileApi.get(), profileApi.get('catalogos'), ...resources.map((name) => profileApi.get(name))])
      .then(([profile, catalogs, ...lists]) => {
        if (active) setState({ loading: false, error: null, data: { profile: profile.perfil, catalogs, lists: Object.fromEntries(resources.map((name, i) => [name, lists[i]])) } })
      }).catch((error) => { if (active) setState({ loading: false, data: null, error: error.message }) })
    return () => { active = false }
  }, [preferences, attempt])
  const ready = Boolean(state.data)
  useEffect(() => {
    if (!ready || !location.hash) return
    const id = location.hash.slice(1)
    if (!['datos-personales', 'formacion-academica', 'experiencia', 'idiomas', 'preferencias', 'disponibilidad'].includes(id)) return
    const heading = document.getElementById(id)
    heading?.focus({ preventScroll: true })
    heading?.scrollIntoView?.({ block: 'start' })
  }, [ready, location.hash])
  const title = preferences ? 'Idiomas, preferencias y disponibilidad' : 'Mi perfil académico'
  if (state.loading || state.error) return <ProfileLayout><h1>{title}</h1>
    {state.loading ? <p role="status"><Icon name="loading" />Cargando tu perfil…</p> : <><Message>{state.error}</Message><Button icon="refresh" onClick={() => { setState({ loading: true, data: null, error: null }); setAttempt(attempt + 1) }}>Reintentar carga</Button></>}
  </ProfileLayout>
  const { profile, catalogs, lists } = state.data
  const fields = profileFields(catalogs)
  const catalogName = (type, id) => catalogs[type].find((row) => row.id === id)?.nombre || 'Sin declarar'
  const choiceName = (type, value) => catalogs[type].find((row) => row.valor === value)?.nombre || 'Sin declarar'
  async function saveProfile(data) {
    const { nombre, ...personal } = data
    let result
    try { result = await profileApi.write('', 'PATCH', personal) }
    catch (failure) {
      throw new ApiError('No se pudo confirmar el guardado del perfil.' + (nombre !== undefined && nombre.trim() !== user.nombre ? ' No se intentó guardar el nombre; los cambios siguen pendientes.' : '') + ' ' + failure.message, failure.status, failure.fields)
    }
    setState((current) => ({ ...current, data: { ...current.data, profile: result.perfil } }))
    if (nombre !== undefined && nombre.trim() !== user.nombre) {
      try { await updateName(nombre.trim()) }
      catch (failure) {
        throw new ApiError('Los datos del perfil se guardaron, pero el nombre no pudo guardarse. Conservamos el nombre pendiente para que puedas reintentarlo. ' + failure.message, failure.status, failure.fields)
      }
    }
  }
  const sections = preferences ? [
    { resource: 'idiomas', anchorId: 'idiomas', title: 'Idiomas declarados', singular: 'idioma', describe: (row) => `${catalogName('idiomas', row.idioma)} · ${row.nivel || 'Nivel sin declarar'}` },
    { resource: 'preferencias', anchorId: 'preferencias', title: 'Preferencias de estudio', singular: 'preferencia', describe: (row) => `${choiceName('niveles', row.nivel)} · ${choiceName('modalidades', row.modalidad)}` },
    { resource: 'areas', title: 'Áreas de interés', singular: 'área', describe: (row) => catalogName('areas', row.area) },
    { resource: 'destinos', title: 'Países de interés', singular: 'destino', describe: (row) => catalogName('paises', row.pais) },
  ] : [
    { resource: 'formaciones', anchorId: 'formacion-academica', title: 'Formación académica', singular: 'formación', describe: (row) => `${row.carrera} · ${choiceName('estados', row.estado_estudios)}` },
    { resource: 'experiencias', anchorId: 'experiencia', title: 'Experiencia relevante', singular: 'experiencia', describe: (row) => `${row.cargo || 'Actividad sin cargo declarado'} · ${row.fecha_inicio} — ${row.actual ? 'Actualidad' : row.fecha_fin}` },
  ]
  return <ProfileLayout>
    <h1>{title}</h1><p className="subtitle">{preferences ? 'Declara lo que sabes y las condiciones en las que puedes estudiar.' : 'Datos declarados. No realizamos validación documental.'}</p>
    {!preferences && <section className="profile-card"><h2 id="datos-personales" className="profile-anchor" tabIndex={-1}>Datos personales y residencia</h2>
      <ProfileForm fields={[{ name: 'nombre', label: 'Nombre visible', maxLength: 180, required: true,
        validate: value => !value.trim() ? 'El nombre no puede estar vacío.' : value.trim().length > 180 ? 'El nombre no puede superar 180 caracteres.' : null }, ...fields.personal]}
        initial={{ ...profile, nombre: user.nombre }} onSubmit={saveProfile} label="Guardar datos personales" />
    </section>}
    {!profile && <Message kind="info">Guarda primero los datos personales para empezar tu perfil. Los datos opcionales pueden quedar sin declarar. {preferences && <Link to="/perfil"><Icon name="profile" /><span>Ir a datos personales</span></Link>}</Message>}
    {profile && <>
      {preferences && <p className="profile-note accent-note">Solo solicitamos idioma y nivel declarado. La entidad oferente solicitará y verificará los certificados cuando una beca los exija.</p>}
      {sections.map((section) => <ProfileRecords key={section.resource} {...section} fields={fields[section.resource]} initial={lists[section.resource]} />)}
      {preferences && <section className="profile-card"><h2 id="disponibilidad" className="profile-anchor" tabIndex={-1}>Disponibilidad declarada</h2>
        <p className="profile-note">Sin declarar significa información pendiente, no una respuesta negativa. La dedicación indica tiempo disponible; las preferencias no son condiciones obligatorias de elegibilidad.</p>
        <ProfileForm fields={fields.availability} initial={profile} onSubmit={saveProfile} label="Guardar disponibilidad" />
      </section>}
    </>}
    <Link className="secondary-link" to={preferences ? '/perfil' : '/preferencias'}><Icon name={preferences ? "back" : "preferences"} /><span>{preferences ? 'Volver a formación' : 'Ir a idiomas y preferencias'}</span></Link>
  </ProfileLayout>
}
