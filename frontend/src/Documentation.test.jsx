import { expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Documentation } from './pages/OfferDetail'
import OfferForm from './components/OfferForm'
import { requirementFields } from './pages/offerFields'

const catalogs = { paises: [], areas: [], idiomas: [], tipos_requisito: [{ id: 1, codigo: 'DOCUMENTO' }, { id: 2, codigo: 'ACREDITACION' }] }
const offer = { opciones: [{ id: 9, programa: 'Programa de prueba' }], requisitos: [
  { id: 1, tipo_requisito: 1, obligatorio: true, texto_original: 'Presentar ante la entidad', valor_estructurado: { documento: 'Título o certificado', condiciones: 'Cuando esté en emisión', url_documento: 'https://example.org/formulario' } },
  { id: 2, tipo_requisito: 2, opcion_estudio: 9, obligatorio: false, valor_estructurado: { certificados_admitidos: 'Certificado <b>externo</b>', vigencia: 'Según las bases' }, detalle_acreditacion: 'Cuando corresponda' },
] }
const documentType = { codigo: 'DOCUMENTO', esquema_valor: { campos: {
  documento: { label: 'Nombre del documento', kind: 'text', required: true },
  condiciones: { label: 'Condiciones o alternativas según las bases', kind: 'text' },
} } }
it('crea un documento común con complementos cerrados y sin marcar revisión', async () => {
  const save = vi.fn()
  render(<OfferForm fields={requirementFields(documentType, catalogs, [])} onSubmit={save} />)
  expect(document.querySelector('details')).not.toHaveAttribute('open')
  expect(screen.getByLabelText('Documento complementario')).not.toBeVisible()
  expect(screen.getByRole('option', { name: 'Toda la convocatoria' }).selected).toBe(true)
  await userEvent.type(screen.getByLabelText(/Nombre del documento/), 'Identidad')
  await userEvent.type(screen.getByLabelText(/Descripción e instrucciones/), 'Presentar copia')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ opcion_estudio: null, regla_documento: 'Identidad', validado: '', documento_exigido: null, detalle_acreditacion: null }))
})
it('conserva complementos antiguos al editar aunque se cierre su apartado', async () => {
  const save = vi.fn()
  render(<OfferForm fields={requirementFields(documentType, catalogs, [])} initial={{ regla_documento: 'Título', documento_exigido: 'Anexo histórico', detalle_acreditacion: 'Condición histórica', validado: false }} onSubmit={save} />)
  expect(screen.getByLabelText('Documento complementario')).toBeVisible()
  await userEvent.click(screen.getByText('Información documental complementaria (opcional)'))
  await userEvent.type(screen.getByLabelText(/Nombre del documento/), ' oficial')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ regla_documento: 'Título oficial', documento_exigido: 'Anexo histórico', detalle_acreditacion: 'Condición histórica', validado: false }))
})
it('mantiene las condiciones de acreditación como campo principal', () => {
  const type = { codigo: 'ACREDITACION', esquema_valor: { campos: { certificados_admitidos: { label: 'Certificados admitidos', kind: 'text' } } } }
  render(<OfferForm fields={requirementFields(type, catalogs, [])} onSubmit={vi.fn()} />)
  expect(screen.getByLabelText('Condiciones o alternativas según las bases')).toBeVisible()
  expect(screen.getByLabelText('Documento complementario')).not.toBeVisible()
})
it('separa documentación común y de opción, conserva alternativas y enlaces sin HTML', () => {
  render(<Documentation offer={offer} catalogs={catalogs} />)
  expect(screen.getAllByText('Título o certificado')).toHaveLength(1)
  expect(screen.getByText('Cuando esté en emisión')).toBeVisible()
  expect(screen.getByText('Cuando corresponda')).toBeVisible()
  expect(screen.getByRole('heading', { name: /Documentos de la opción/ })).toBeVisible()
  expect(screen.getByText('No obligatorio según lo registrado')).toBeVisible()
  // Los enlaces de documentos se listan en «Bases y documentos oficiales», no en cada requisito.
  expect(screen.queryByRole('link', { name: /Consultar documento o formulario oficial/ })).not.toBeInTheDocument()
  expect(screen.getByText('Certificado <b>externo</b>')).toBeVisible()
  expect(document.querySelector('b')).toBeNull()
  expect(screen.getByText(/BecaNexo no los recibe ni acredita/)).toBeVisible()
})
it('informa documentación desconocida y no fabrica enlaces', () => {
  render(<Documentation offer={{ opciones: [], requisitos: [] }} catalogs={catalogs} />)
  expect(screen.getByText('Consulta las bases oficiales para confirmar la documentación requerida')).toBeVisible()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})
it('no ofrece enlaces con esquemas inseguros', () => {
  render(<Documentation offer={{ opciones: [], requisitos: [{ ...offer.requisitos[0], valor_estructurado: { documento: 'Documento', url_documento: 'javascript:alert(1)' } }] }} catalogs={catalogs} />)
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})
it('edita documentación en controles sin JSON preservando ámbito y condiciones', async () => {
  const type = { codigo: 'DOCUMENTO', esquema_valor: { campos: {
    documento: { label: 'Nombre del documento', kind: 'text', required: true },
    condiciones: { label: 'Condiciones o alternativas según las bases', kind: 'text' },
    url_documento: { label: 'Enlace oficial del documento o formulario', kind: 'url' },
  } } }
  const save = vi.fn()
  render(<OfferForm fields={requirementFields(type, catalogs, [{ id: 9, nivel: 'grado', modalidad: 'virtual' }])} initial={{ regla_documento: 'Título', regla_condiciones: 'Cuando corresponda', obligatorio: true }} onSubmit={save} />)
  await userEvent.type(screen.getByLabelText(/Nombre del documento/), ' o certificado')
  await userEvent.selectOptions(screen.getByLabelText(/Ámbito/), '9')
  await userEvent.type(screen.getByLabelText('Enlace oficial del documento o formulario'), 'https://example.org/formulario')
  await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ regla_documento: 'Título o certificado', regla_condiciones: 'Cuando corresponda', opcion_estudio: 9, obligatorio: true, regla_url_documento: 'https://example.org/formulario' }))
  expect(within(document.body).queryByLabelText(/JSON/)).not.toBeInTheDocument()
})
