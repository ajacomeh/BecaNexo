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
        <p>La afinidad temática ordena las convocatorias públicas dentro de cada resultado de requisitos. No convierte un incumplimiento en elegibilidad.</p>
        <p className="small-note">Los filtros, el orden y la paginación de «Todas las becas» no se aplican aquí. Al volver, conservarás tu búsqueda.</p></div>
      {state?.data && <Button type="button" icon="refresh" onClick={onRefresh}>Actualizar recomendaciones</Button>}
    </div>
    {!catalogs && catalogError && <><Message>{catalogError}</Message><Button type="button" icon="refresh" onClick={onRetryCatalog}>Reintentar catálogo</Button></>}
    {(!state || (state.data && !catalogs && !catalogError)) && <p role="status">Calculando afinidad y cargando oportunidades…</p>}
    {state?.error && <><Message>{state.error}</Message><Button type="button" icon="refresh" onClick={onRefresh}>Reintentar recomendaciones</Button></>}
    {state?.data && catalogs && <>
      {state.data.aviso && <p className="small-note">{state.data.aviso}</p>}
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
