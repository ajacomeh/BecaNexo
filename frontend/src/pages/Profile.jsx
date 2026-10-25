import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { profileApi } from '../api/client'
import { useAuth } from '../auth/context'
import ProfileLayout from '../components/ProfileLayout'
import ProfileForm from '../components/ProfileForm'
import ProfileRecords from '../components/ProfileRecords'
import Button from '../components/Button'
import Message from '../components/Message'
import { profileFields } from './profileFields'

export default function Profile({ preferences = false }) {
  const { user } = useAuth()
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
  const title = preferences ? 'Idiomas, preferencias y disponibilidad' : 'Mi perfil académico'
  if (state.loading || state.error) return <ProfileLayout><h1>{title}</h1>
    {state.loading ? <p role="status">Cargando tu perfil…</p> : <><Message>{state.error}</Message><Button onClick={() => { setState({ loading: true, data: null, error: null }); setAttempt(attempt + 1) }}>Reintentar carga</Button></>}
  </ProfileLayout>
  const { profile, catalogs, lists } = state.data
  const fields = profileFields(catalogs)
  const catalogName = (type, id) => catalogs[type].find((row) => row.id === id)?.nombre || 'Sin declarar'
  const choiceName = (type, value) => catalogs[type].find((row) => row.valor === value)?.nombre || 'Sin declarar'
  async function saveProfile(data) {
    const result = await profileApi.write('', 'PATCH', data)
    setState((current) => ({ ...current, data: { ...current.data, profile: result.perfil } }))
  }
  const sections = preferences ? [
    { resource: 'idiomas', title: 'Idiomas declarados', singular: 'idioma', describe: (row) => `${catalogName('idiomas', row.idioma)} · ${row.nivel || 'Nivel sin declarar'}` },
    { resource: 'preferencias', title: 'Preferencias de estudio', singular: 'preferencia', describe: (row) => `${choiceName('niveles', row.nivel)} · ${choiceName('modalidades', row.modalidad)}` },
    { resource: 'areas', title: 'Áreas de interés', singular: 'área', describe: (row) => catalogName('areas', row.area) },
    { resource: 'destinos', title: 'Países de interés', singular: 'destino', describe: (row) => catalogName('paises', row.pais) },
  ] : [
    { resource: 'formaciones', title: 'Formación académica', singular: 'formación', describe: (row) => `${row.carrera} · ${choiceName('estados', row.estado_estudios)}` },
    { resource: 'experiencias', title: 'Experiencia relevante', singular: 'experiencia', describe: (row) => `${row.cargo || 'Actividad sin cargo declarado'} · ${row.fecha_inicio} — ${row.actual ? 'Actualidad' : row.fecha_fin}` },
  ]
  return <ProfileLayout>
    <h1>{title}</h1><p className="subtitle">{preferences ? 'Declara lo que sabes y las condiciones en las que puedes estudiar.' : 'Datos declarados. No realizamos validación documental.'}</p>
    {!preferences && <section className="profile-card"><h2>Datos personales y residencia</h2>
      <p className="profile-note">Nombre visible: <strong>{user.nombre}</strong>. Nacionalidad: <strong>Ecuatoriana</strong> · Alcance del sistema. Puedes residir en otro país.</p>
      <ProfileForm fields={fields.personal} initial={profile || {}} onSubmit={saveProfile} label="Guardar datos personales" />
    </section>}
    {!profile && <Message kind="info">Guarda primero los datos personales para empezar tu perfil. Los datos opcionales pueden quedar sin declarar. {preferences && <Link to="/perfil">Ir a datos personales</Link>}</Message>}
    {profile && <>
      {preferences && <p className="profile-note accent-note">Solo solicitamos idioma y nivel declarado. La entidad oferente solicitará y verificará los certificados cuando una beca los exija.</p>}
      {sections.map((section) => <ProfileRecords key={section.resource} {...section} fields={fields[section.resource]} initial={lists[section.resource]} />)}
      {preferences && <section className="profile-card"><h2>Disponibilidad declarada</h2>
        <p className="profile-note">Sin declarar significa información pendiente, no una respuesta negativa. Las preferencias no son condiciones obligatorias de elegibilidad.</p>
        <ProfileForm fields={fields.availability} initial={profile} onSubmit={saveProfile} label="Guardar disponibilidad" />
      </section>}
    </>}
    <Link className="secondary-link" to={preferences ? '/perfil' : '/preferencias'}>{preferences ? 'Volver a formación' : 'Ir a idiomas y preferencias'}</Link>
  </ProfileLayout>
}
