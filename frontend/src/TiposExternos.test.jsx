import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Comparison from './components/Comparison'
import { AuthContext } from './auth/context'
import { offersApi } from './api/client'
import { isExternal } from './pages/offerFields'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const catalogs = { paises: [], idiomas: [], areas: [], tipos_requisito: [
  { codigo: 'CONDICION_ADMINISTRATIVA', nombre: 'Condición administrativa' }, { codigo: 'DOCUMENTO', nombre: 'Documento externo' }] }
const req = (id, tipo) => ({ id, tipo, descripcion: `Condición ${id}`, obligatorio: true, ambito: 'comun', resultado: 'desconocido',
  explicacion: 'La entidad oferente debe comprobar esta condición.', dato_declarado: null, condicion_exigida: { valores: {} }, comprobacion_externa: true })

it('explica que la condición administrativa la comprueba la entidad en sus registros y no la da por cumplida', async () => {
  vi.spyOn(offersApi, 'get').mockResolvedValue({ aviso: '', criterio_destacada: '', opcion_destacada_id: 1, opciones: [{
    id: 1, programa: 'Programa', nivel: 'maestria', modalidad: 'virtual', destinos: ['Ecuador'], resultado: 'desconocido', resumen: 'Pendiente',
    requisitos: [req(1, 'CONDICION_ADMINISTRATIVA'), req(2, 'DOCUMENTO')], verificaciones_externas_pendientes: 2 }] })
  render(<MemoryRouter><AuthContext.Provider value={{ user: { id: 1, rol: 'postulante' } }}><Comparison offerId={3} catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: 'Comparar requisitos' }))
  expect(await screen.findByText(/comprueba esta condición en sus registros administrativos\. BecaNexo no la da por cumplida/)).toBeVisible()
  // Los documentos conservan su mensaje de siempre.
  expect(screen.getByText(/comprueba los documentos y certificados/)).toBeVisible()
  expect(screen.getByText('Por confirmar (2)')).toBeVisible()
})

it('reconoce los tipos externos por el operador de su contrato, incluido el tipo nuevo', () => {
  const tipo = (codigo, operador) => ({ codigo, esquema_valor: { operadores: [operador] } })
  expect(['OTRO', 'DOCUMENTO', 'ACREDITACION', 'CONDICION_ADMINISTRATIVA'].map(codigo => isExternal(tipo(codigo, 'externo')))).toEqual([true, true, true, true])
  expect(isExternal(tipo('NACIONALIDAD', 'pertenece'))).toBe(false)
  expect(isExternal(undefined)).toBe(false)
})
