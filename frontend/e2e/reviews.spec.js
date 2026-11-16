import { test, expect } from '@playwright/test'

const list = (results = []) => ({ results, count: results.length, page: 1, page_size: 12 })

test('detalle de Rastreo compacto y acceso al borrador a tres anchuras', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 99, nombre: 'Administradora de prueba', rol: 'administrador' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'solo-prueba' } })
    if (path === '/api/gestion/rastreo/publicaciones/5/') return route.fulfill({ json: {
      id: 5, titulo: 'Beca nacional de prueba con título extenso para comprobar la adaptación móvil',
      fuente: { id: 1, nombre: 'SIAU de prueba' }, url_original: 'https://example.org/publicacion/con/ruta/muy/larga/para/comprobar/desbordamiento',
      primera_deteccion: '2026-11-11T10:00:00Z', ultima_deteccion: '2026-11-12T10:00:00Z',
      version_observada_id: 7, convocatoria_id: 9,
      cierre_extraido: { texto_original: 'Cierra el 12 de noviembre de 2026' },
      clasificacion_borrador: { estado: 'apta', motivo: 'Ficha individual identificada.' },
      borrador: { id: 9, revision: 'pendiente', activa: true,
        bloqueos: ['Confirmar requisitos de la versión vigente'], observaciones: ['Revisar bases documentales'] },
    } })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/7/') return route.fulfill({ json: {
      id: 7, numero: 2, estado_extraccion: 'completa', version_extractor: 'extractor/1', version_contrato: 'contrato/1',
      datos_extraidos: { titulo: { texto_original: 'Beca nacional de prueba' },
        requisitos: { texto_original: 'Ser ciudadano ecuatoriano' },
        enlaces_bases: [{ url: 'https://example.org/bases/con/una/ruta/larga.pdf' }] },
      texto_extraido: 'Texto íntegro de la ficha de prueba', advertencias: ['Documento por revisar'],
    } })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/') return route.fulfill({ json: list([{ id: 7, numero: 2, creada_en: '2026-11-12T10:00:00Z' }]) })
    if (path === '/api/gestion/rastreo/publicaciones/5/versiones/7/documentos/') return route.fulfill({ json: list([{ id: 12, rol: 'ficha_html', mime: 'text/html', tamano_bytes: 400, sha256: 'a'.repeat(64), url_original: 'https://example.org/ficha' }]) })
    if (path === '/api/gestion/rastreo/publicaciones/5/observaciones/') return route.fulfill({ json: list([{ id: 3, observada_en: '2026-11-12T10:00:00Z', resultado: 'nueva', version_id: 7, ejecucion_id: 8, estado_ejecucion: 'finalizada' }]) })
    return route.fulfill({ json: list() })
  })

  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/gestion/rastreo/publicaciones/5')
    await expect(page.getByRole('link', { name: 'Abrir borrador en Convocatorias' })).toHaveAttribute('href', '/gestion/convocatorias/9')
    await expect(page.getByText('Confirmar requisitos de la versión vigente')).toBeVisible()
    await expect(page.getByText('Ser ciudadano ecuatoriano').first()).toBeVisible()
    const fieldPadding = await page.locator('.crawl-evidence-group .crawl-data > div').first().evaluate(node => getComputedStyle(node).paddingLeft)
    expect(parseFloat(fieldPadding)).toBeGreaterThanOrEqual(14)
    await expect(page.getByRole('heading', { name: 'Evidencias y versiones' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Historial' })).toBeVisible()
    await page.getByText('Evidencia estructurada completa').click()
    await expect(page.getByRole('heading', { name: 'Requisitos', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Enlaces y documentos' })).toBeVisible()
    await page.getByText('Referencias de origen (1)').click()
    await expect(page.getByText('https://example.org/bases/con/una/ruta/larga.pdf').last()).toBeVisible()
    await expect(page.getByText('Texto íntegro de la ficha de prueba')).toBeHidden()
    await page.getByText('Texto original completo').click()
    await expect(page.getByText('Texto íntegro de la ficha de prueba')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Registrar revisión' })).toHaveCount(0)
    await expect(page.getByText('Propuesta de integración')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})

test('candidatos del editor mantienen tarjetas y acciones sin desbordar en móvil', async ({ page }) => {
  const offer = { id: 7, titulo: 'Beca de prueba', descripcion: 'Ficha sintética', estado: 'borrador',
    revision: 'pendiente', activa: true, version: 1, institucion: null, origen_automatico: { publicacion_id: 5 },
    tipo_beca: null, cierre: null, cierre_dia: null, opciones: [], beneficios: [], requisitos: [], areas: [] }
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 99, nombre: 'Admin de prueba', rol: 'administrador' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'solo-prueba' } })
    if (path === '/api/gestion/convocatorias/7/') return route.fulfill({ json: offer })
    if (path === '/api/gestion/rastreo/convocatorias/7/origen/') return route.fulfill({ json: {
      automatico: true, aplicacion: null, publicacion_id: 5, version_id: 2,
      bloqueos_actuales: [], datos_iniciales: {}, candidatos_editables: { requisitos: [
        { texto_original: 'Promedio mínimo de 8,5', tipo_sugerido: 'PROMEDIO', estado: 'identificado', metodo: 'regla',
          valor_sugerido: { minimo: '8,5' }, procedencia: { version_id: 2, documento_id: 8 } },
        { texto_original: 'Una condición académica extensa por comprobar '.repeat(12), estado: 'ambiguo',
          procedencia: { version_id: 2 } }], opciones: [] } } })
    if (path === '/api/gestion/instituciones/') return route.fulfill({ json: list([]) })
    if (path === '/api/gestion/becas/catalogos/' || path === '/api/becas/catalogos/') return route.fulfill({ json: {
      paises: [], areas: [], niveles: [], modalidades: [], tipos_beca: [], tipos_requisito: [] } })
    return route.fulfill({ json: list([]) })
  })
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/gestion/convocatorias/7')
    await page.getByText('Requisitos extraídos para revisar (2)').click()
    await expect(page.locator('.origin-candidate')).toHaveCount(2)
    await expect(page.locator('.origin-candidate').first()).toContainText('Tipo: PROMEDIO')
    await expect(page.locator('.origin-candidate').last()).toContainText('Estado: ambiguo')
    await expect(page.getByRole('button', { name: 'Preparar en editor' }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})
