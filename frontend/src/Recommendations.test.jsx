import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Recommendations from './components/Recommendations'
import { offersApi } from './api/client'
import { AuthContext } from './auth/context'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const catalogs = { paises: [], tipos_requisito: [] }
const offer = { id: 7, titulo: 'Beca de ingeniería', institucion: { nombre: 'Entidad' },
  estado: 'sin_fecha', beneficios: [], opciones: [] }

it('consulta al solicitar, distingue afinidad de elegibilidad y conserva el enlace de detalle', async () => {
  const get = vi.spyOn(offersApi, 'get').mockResolvedValue({ aviso: 'Comparación orientativa', results: [
    { convocatoria: offer, elegibilidad: 'no_cumple', afinidad: { estado: 'calculada', explicacion: 'Se compararon áreas declaradas.' }, preferencias: { declaradas: true, coincidencias: ['nivel de estudio'] } },
  ] })
  render(<MemoryRouter><AuthContext.Provider value={{ user: { id: 1, rol: 'postulante' } }}><Recommendations catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
  expect(get).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Ver recomendaciones' }))
  expect(await screen.findByText('Beca de ingeniería')).toBeVisible()
  expect(get).toHaveBeenCalledWith('becas/recomendaciones')
  expect(screen.getByText(/Hay un incumplimiento obligatorio declarado/)).toBeVisible()
  expect(screen.getByText(/Calculada con el modelo local/)).toBeVisible()
  expect(screen.getByText(/Coinciden nivel de estudio/)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Ver detalle' })).toHaveAttribute('href', '/becas/7')
})

it('muestra error y permite reintentar sin presentar afinidad inventada', async () => {
  const get = vi.spyOn(offersApi, 'get').mockRejectedValueOnce(new Error('Sin conexión'))
    .mockResolvedValueOnce({ aviso: 'Orientativo', results: [] })
  render(<MemoryRouter><AuthContext.Provider value={{ user: { id: 1, rol: 'postulante' } }}><Recommendations catalogs={catalogs} /></AuthContext.Provider></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: 'Ver recomendaciones' }))
  expect(await screen.findByText('Sin conexión')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Ver recomendaciones' }))
  expect(await screen.findByText('No hay convocatorias públicas para recomendar.')).toBeVisible()
  expect(get).toHaveBeenCalledTimes(2)
})
