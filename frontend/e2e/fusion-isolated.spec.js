import { test, expect } from '@playwright/test'

const list = (results) => ({ count: results.length, page: 1, page_size: 12, results })

test('borrador automático visible solo en administración y revisable a tres anchuras', async ({ page }) => {
  let offer = { id: 7, titulo: 'Beca nacional sintética de prueba', descripcion: 'Ficha de prueba',
    estado: 'borrador', revision: 'pendiente', activa: true, version: 1,
    institucion: null, origen_automatico: { publicacion_id: 5 },
    tipo_beca: null, tipo_beca_nombre: null, cierre: null, cierre_dia: null,
    opciones: [], beneficios: [], requisitos: [], areas: [] }
  const institution = { id: 3, nombre: 'Entidad ecuatoriana sintética' }
  const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }],
    areas: [], niveles: [], modalidades: [], tipos_beca: [], tipos_requisito: [] }
  const publication = { id: 5, titulo: offer.titulo, fuente: { id: 1, nombre: 'SIAU sintético' },
    url_original: 'https://example.org/ficha-sintetica', version_observada_id: 2,
    primera_deteccion: '2026-11-11T10:00:00Z', ultima_deteccion: '2026-11-12T10:00:00Z' }
  const proposal = { id: 9, hash_propuesta: 'a'.repeat(64), version_id: 2,
    observacion_base_id: 3, revisiones: [], datos: { titulo: 'Título revisado' },
    procedencia: [{ campo: 'titulo', evidencia_id: 8, localizador: 'Ficha', motivo: 'Revisado' }],
    pendientes: { bloqueos: [], pendientes_publicacion: [], creacion_habilitada: false },
    autor: { nombre: 'Administrador sintético' } }
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 99, nombre: 'Administrador sintético', rol: 'administrador' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'token-sintetico' } })
    if (path === '/api/gestion/convocatorias/') return route.fulfill({ json: list([offer]) })
    if (path === '/api/gestion/convocatorias/7/') {
      if (route.request().method() === 'PATCH') {
        const data = route.request().postDataJSON()
        offer = { ...offer, ...data, institucion: data.institucion === 3 ? institution : null,
          version: offer.version + 1, revision: 'pendiente' }
      }
      return route.fulfill({ json: offer })
    }
    if (path === '/api/gestion/instituciones/') return route.fulfill({ json: { ...list([institution]), page_size: 50 } })
    if (path === '/api/gestion/rastreo/publicaciones/5/') return route.fulfill({ json: publication })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/') return route.fulfill({ json: list([
      { id: 2, numero: 1, creada_en: '2026-11-11T10:00:00Z' }]) })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/2/') return route.fulfill({ json: {
      id: 2, numero: 1, estado_extraccion: 'completa', advertencias: [],
      texto_extraido: 'Ficha sintética conservada', datos_extraidos: {} } })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/2/documentos/') return route.fulfill({ json: list([
      { id: 8, evidencia_id: 8, rol: 'ficha_html', mime: 'text/html', tamano_bytes: 40, sha256: 'a'.repeat(64) }]) })
    if (path === '/api/gestion/rastreo/publicaciones/5/propuesta/') return route.fulfill({ json: {
      ...list([proposal]), borrador_automatico_id: 7,
      contexto: { version_id: 2, observacion_base_id: 3, revisiones: [] } } })
    if (path === '/api/gestion/rastreo/publicaciones/5/observaciones/') return route.fulfill({ json: list([]) })
    if (path.endsWith('/revisiones/')) return route.fulfill({ json: list([]) })
    if (path === '/api/gestion/rastreo/convocatorias/7/origen/') return route.fulfill({ json: {
      aplicacion: null, automatico: true, publicacion_id: 5, version_id: 2,
      version_actual_id: 3, version_convocatoria: offer.version,
      cambio_relevante: true, revision_confirmada: false,
      bloqueos_actuales: ['Confirmar entidad oferente ecuatoriana', 'Revisar la versión nueva'],
      datos_iniciales: { titulo: offer.titulo, requisitos_originales: 'Condición sintética larga '.repeat(20),
        entidad_mencionada: 'Entidad ecuatoriana sintética' },
      candidatos_editables: { requisitos: [], opciones: [], otros_campos: { beneficios: [{
        texto_original: 'Por una sola vez USD 828.97 para manutención', concepto_sugerido: 'manutención',
        monto: 828.97, moneda: 'USD', porcentaje: null, tope_original: null,
        procedencia: { version_id: 2 } }] } },
    } })
    if (path === '/api/gestion/becas/catalogos/' || path === '/api/becas/catalogos/') return route.fulfill({ json: catalogs })
    if (path === '/api/becas/') return route.fulfill({ json: list([]) })
    return route.fulfill({ status: 404, json: { detail: `Ruta simulada no definida: ${path}` } })
  })

  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/gestion/convocatorias', { waitUntil: 'domcontentloaded' })
    await expect(page.getByText('Borrador del rastreo · Publicación 5')).toBeVisible()
    await page.getByRole('link', { name: 'Editar y revisar' }).click()
    await expect(page.getByRole('heading', { name: 'Borrador generado por rastreo' })).toBeVisible()
    await expect(page.getByText('Revisar la versión nueva')).toBeVisible()
    await expect(page.getByRole('link', { name: /Consultar ficha/ })).toHaveAttribute('href', '/gestion/rastreo/publicaciones/5')
    await page.getByText('Datos de origen conservados').click()
    await expect(page.getByText(/Condición sintética larga/)).toBeVisible()
    await page.getByText('Beneficios interpretados para revisar').click()
    await page.getByRole('button', { name: 'Preparar en editor' }).click()
    await expect(page.getByLabel('Importe fijo (no es tope)')).toHaveValue('828.97')
    await expect(page.getByLabel('Concepto financiado')).toHaveValue('manutención')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.getByRole('link', { name: /Consultar ficha/ }).click()
    await page.getByRole('button', { name: 'Continuar propuesta' }).click()
    await expect(page.getByRole('heading', { name: 'Aplicar cambios al borrador vinculado' })).toBeVisible()
    await expect(page.getByRole('checkbox', { name: /Título:/ })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})
