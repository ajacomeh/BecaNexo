import CatalogCard from './CatalogCard'
import Button from './Button'
import Message from './Message'

const eligibility = {
  cumple: 'Requisitos obligatorios comparables coinciden según lo declarado',
  desconocido: 'Falta información para confirmar los requisitos',
  no_cumple: 'Hay un incumplimiento obligatorio declarado',
}

export default function Recommendations({ catalogs, state, onRefresh, catalogError, onRetryCatalog }) {
  return <section aria-labelledby="recommendations-title">
    <div className="catalog-recommendations-heading">
      <div><h2 id="recommendations-title">Recomendaciones según tu perfil</h2>
        <p>Becas ordenadas según tus requisitos y afinidad académica.</p>
        <p className="small-note">La afinidad temática no garantiza elegibilidad ni adjudicación.</p></div>
      {state?.data && <Button type="button" icon="refresh" onClick={onRefresh}>Actualizar recomendaciones</Button>}
    </div>
    {!catalogs && catalogError && <><Message>{catalogError}</Message><Button type="button" icon="refresh" onClick={onRetryCatalog}>Reintentar catálogo</Button></>}
    {(!state || (state.data && !catalogs && !catalogError)) && <p role="status">Calculando afinidad y cargando oportunidades…</p>}
    {state?.error && <><Message>{state.error}</Message><Button type="button" icon="refresh" onClick={onRefresh}>Reintentar recomendaciones</Button></>}
    {state?.data && catalogs && <>
      {state.data.results.length === 0 && <p>No hay convocatorias públicas para recomendar.</p>}
      <div className="offer-grid">{state.data.results.map(item => <CatalogCard key={item.convocatoria.id} offer={item.convocatoria} catalogs={catalogs} recommendation={{
        elegibilidad: item.elegibilidad,
        requirements: eligibility[item.elegibilidad],
        affinity: `${item.afinidad.estado === 'calculada' ? 'Calculada con el modelo local' : 'Pendiente'}. ${item.afinidad.explicacion}`,
        preferences: `${!item.preferencias?.declaradas ? 'Sin declarar' : item.preferencias.coincidencias.length ? `Coinciden ${item.preferencias.coincidencias.join(', ')}.` : 'No hay coincidencias declaradas en nivel, modalidad o destino.'} No determinan elegibilidad.`,
      }} />)}</div>
    </>}
  </section>
}
