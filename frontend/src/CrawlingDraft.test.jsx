import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import CrawlingDraft from './components/CrawlingDraft'
import { offersApi } from './api/client'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const proposal = { id: 41, hash_propuesta: 'a'.repeat(64), observacion_base_id: 12,
  revisiones: [5, 6], datos: { institucion: 2, titulo: 'Beca sintética',
    opciones: [{ id: 'o1', texto: 'Programa sintético', nivel: 'maestria', modalidad: 'virtual', paises: ['EC'] }],
    beneficios: [{ id: 'b1', concepto: 'Matrícula', tope: '$3000' }], requisitos: [] } }
const props = { proposal, result: { bloqueos: [], pendientes_publicacion: [{ id: 'TOPE_NO_REPRESENTADO:beneficios.b1', codigo: 'TOPE_NO_REPRESENTADO', campo: 'beneficios.b1', motivo: 'Tope sin representación' }] },
  countries: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], types: [], documents: [{ evidencia_id: 9, rol: 'bases_pdf' }] }
function show(overrides = {}) {
  render(<MemoryRouter initialEntries={['/rastreo']}><Routes><Route path="/rastreo" element={<CrawlingDraft {...props} {...overrides} onCreated={vi.fn()} />} /><Route path="/gestion/convocatorias/:id" element={<p>Editor abierto</p>} /></Routes></MemoryRouter>)
}

it('confirma todos los candidatos y crea solo la opción seleccionada antes de abrir el editor', async () => {
  const write = vi.spyOn(offersApi, 'write').mockResolvedValue({ convocatoria_id: 25 })
  show()
  await userEvent.type(screen.getByLabelText('Correspondencia con la entidad oferente revisada'), 'Entidad cotejada con bases')
  await userEvent.click(screen.getAllByLabelText('Incluir en el borrador')[0])
  await userEvent.type(screen.getByLabelText('Motivo y respaldo del mapeo'), 'Programa y destinos confirmados')
  await userEvent.click(screen.getByLabelText(/Confirmo el contenido seleccionado/))
  await userEvent.click(screen.getByRole('button', { name: 'Crear borrador vinculado' }))
  expect(await screen.findByText('Editor abierto')).toBeVisible()
  expect(write).toHaveBeenCalledWith('gestion/rastreo/propuestas/41/crear-borrador', 'POST', expect.objectContaining({
    confirmados: ['o1', 'b1'], beneficios: [], opciones: [expect.objectContaining({ id: 'o1', datos: expect.objectContaining({ nivel: 'maestria', paises: [1] }) })],
  }))
})

it('conserva confirmación, motivo y clave ante error recuperable', async () => {
  const write = vi.spyOn(offersApi, 'write').mockRejectedValueOnce(new Error('Conflicto sintético')).mockResolvedValueOnce({ convocatoria_id: 25 })
  show()
  await userEvent.type(screen.getByLabelText('Correspondencia con la entidad oferente revisada'), 'Correspondencia comprobada')
  await userEvent.click(screen.getByLabelText(/Confirmo el contenido seleccionado/))
  await userEvent.click(screen.getByRole('button', { name: 'Crear borrador vinculado' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Conflicto sintético')
  expect(screen.getByLabelText('Correspondencia con la entidad oferente revisada')).toHaveValue('Correspondencia comprobada')
  await userEvent.click(screen.getByRole('button', { name: 'Crear borrador vinculado' }))
  expect(await screen.findByText('Editor abierto')).toBeVisible()
  expect(write.mock.calls[0][2].clave_accion).toBe(write.mock.calls[1][2].clave_accion)
})

it('bloquea la creación cuando la validación informa impedimentos', () => {
  show({ result: { bloqueos: [{ id: 'x', motivo: 'Revisión pendiente' }], pendientes_publicacion: [] } })
  expect(screen.getByRole('button', { name: 'Crear borrador vinculado' })).toBeDisabled()
  expect(screen.getByText(/Revisión pendiente/)).toBeVisible()
})
