import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'
import Button from './Button'
import { offersApi } from '../api/client'

const STATES = { borrador: 'Borrador', publicada: 'Publicada', descartada: 'Descartada' }

// Sugerencias de IA local para un borrador: solo rellenan el formulario; guardar sigue siendo decisión del administrador.
// Si no hay nada fiable que sugerir (o la consulta falla), el bloque no aparece.
export default function DraftSuggestions({ offerId, onUseLevel, onUseType }) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let live = true
    offersApi.get(`gestion/convocatorias/${offerId}/sugerencias`)
      .then((result) => { if (live) setData(result) })
      .catch(() => { if (live) setData(null) })
    return () => { live = false }
  }, [offerId])
  const duplicates = data?.duplicados || []
  if (!data || (!data.nivel && !data.tipo_beca && !duplicates.length)) return null
  return <section className="profile-card" aria-labelledby="sugerencias-automaticas">
    <h2 id="sugerencias-automaticas">Sugerencias automáticas</h2>
    <p className="profile-note">Sugerencia automática: confírmala tú. «Usar sugerencia» solo rellena el formulario; nada se guarda hasta que pulses Guardar.</p>
    <ul className="record-list offer-records">
      {data.nivel && <li><span>Nivel de estudio: <strong>{data.nivel.etiqueta}</strong> ({data.nivel.origen})</span>
        <div className="record-actions"><Button icon="add" className="button-light" onClick={() => onUseLevel(data.nivel.valor)}
          aria-label={`Usar sugerencia de nivel: ${data.nivel.etiqueta}`}>Usar sugerencia</Button></div></li>}
      {data.tipo_beca && <li><span>Tipo de beca: <strong>{data.tipo_beca.nombre}</strong> ({data.tipo_beca.origen})</span>
        <div className="record-actions"><Button icon="edit" className="button-light" onClick={() => onUseType(data.tipo_beca.id)}
          aria-label={`Usar sugerencia de tipo de beca: ${data.tipo_beca.nombre}`}>Usar sugerencia</Button></div></li>}
    </ul>
    {duplicates.length > 0 && <>
      <h3>Posibles duplicados</h3>
      <p className="small-note">Revisa antes de decidir.</p>
      <ul className="record-list offer-records" aria-label="Posibles duplicados">{duplicates.map((d) => <li key={d.id}>
        <span><Link to={`/gestion/convocatorias/${d.id}`}>#{d.id} {d.titulo}</Link> · {STATES[d.estado] || d.estado} · {d.motivo}</span></li>)}</ul>
    </>}
  </section>
}
