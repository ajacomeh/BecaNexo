import { useState } from 'react'
import { offersApi } from '../api/client'
import Button from './Button'
import Message from './Message'
import CatalogCard from './CatalogCard'

const eligibility = {
  cumple: 'Requisitos obligatorios comparables coinciden según lo declarado',
  desconocido: 'Falta información para confirmar los requisitos',
  no_cumple: 'Hay un incumplimiento obligatorio declarado',
}

export default function Recommendations({ catalogs }) {
  const [state, setState] = useState({ busy: false, data: null, error: '' })
  const load = async () => {
    if (state.busy) return
    setState({ busy: true, data: null, error: '' })
    try {
      const data = await offersApi.get('becas/recomendaciones')
      setState({ busy: false, data, error: '' })
    } catch (error) {
      setState({ busy: false, data: null, error: error.message })
    }
  }
  return <section className="profile-card" aria-labelledby="recommendations-title">
    <h2 id="recommendations-title">Recomendaciones según tu perfil</h2>
    <p>La afinidad temática ordena todas las convocatorias públicas dentro de cada resultado de requisitos, independientemente de los filtros del catálogo. No convierte un incumplimiento en elegibilidad.</p>
    <Button type="button" busy={state.busy} onClick={load}>{state.busy ? 'Calculando afinidad…' : state.data ? 'Actualizar recomendaciones' : 'Ver recomendaciones'}</Button>
    {state.busy && <p role="status">Calculando con la información actual…</p>}
    <Message>{state.error}</Message>
    {state.data && <><p className="small-note">{state.data.aviso}</p>
      {state.data.results.length === 0 && <p>No hay convocatorias públicas para recomendar.</p>}
      <div className="offer-grid">{state.data.results.map(item => <div className="recommendation-item" key={item.convocatoria.id}>
        <CatalogCard offer={item.convocatoria} catalogs={catalogs} />
        <p><strong>Requisitos:</strong> {eligibility[item.elegibilidad]}</p>
        <p><strong>Afinidad temática:</strong> {item.afinidad.estado === 'calculada' ? 'Calculada con el modelo local' : 'Pendiente'}. {item.afinidad.explicacion}</p>
        <p><strong>Preferencias:</strong> {!item.preferencias?.declaradas ? 'Sin declarar' : item.preferencias.coincidencias.length ? `Coinciden ${item.preferencias.coincidencias.join(', ')}.` : 'No hay coincidencias declaradas en nivel, modalidad o destino.'} No determinan elegibilidad.</p>
      </div>)}</div>
    </>}
  </section>
}
