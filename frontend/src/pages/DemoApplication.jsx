import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { offersApi } from '../api/client'
import OffersLayout from '../components/OffersLayout'
import Icon from '../components/Icon'
import Message from '../components/Message'

export default function DemoApplication() {
  const { id } = useParams()
  const [result, setResult] = useState(null)

  useEffect(() => {
    let live = true
    offersApi.get(`becas/${id}`).then(offer => {
      if (live) setResult({ id, offer })
    }).catch(error => {
      if (live) setResult({ id, error: error.status === 404 ? 'Esta convocatoria no está disponible para consulta.' : error.message })
    })
    return () => { live = false }
  }, [id])

  const current = result?.id === id ? result : null
  const offer = current?.offer && String(current.offer.id) === id ? current.offer : null
  const fictitious = offer?.titulo?.endsWith('(Ficticia)')

  return <OffersLayout><Link className="back-link" to={`/becas/${id}`}><Icon name="back" /><span>Volver al detalle de la beca</span></Link>
    {!current && <p role="status"><Icon name="loading" />Cargando demostración…</p>}
    {current?.error && <Message>{current.error}</Message>}
    {offer && (fictitious ? <section className="offer-detail-hero"><p className="eyebrow">DEMOSTRACIÓN · SIN POSTULACIONES</p><h1>Postulación de demostración</h1>
      <p className="offer-provider">{offer.titulo}</p><p>{offer.institucion?.nombre || 'Oferente no identificado'}</p>
      <p>Esta convocatoria es ficticia. Esta página solo muestra cómo se accedería a una postulación externa; no recibe solicitudes ni datos personales.</p>
      <Link className="secondary-link" to={`/becas/${id}`}>Volver a la convocatoria ficticia</Link>
    </section> : <Message>Esta página de demostración solo corresponde a convocatorias ficticias.</Message>)}
  </OffersLayout>
}
