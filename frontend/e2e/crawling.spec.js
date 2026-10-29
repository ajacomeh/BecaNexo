import { test, expect } from '@playwright/test'

const list = (results) => ({ count: results.length, page: 1, page_size: 12, results })
const p = { id: 1, titulo: 'Publicación sintética para revisión visual', fuente: { id: 1, nombre: 'Fuente sintética' }, url_original: 'https://example.org/' + 'ruta-larga-'.repeat(15), version_observada_id: 1 }
test('bandeja de solo consulta en escritorio y móvil con API simulada', async ({ page }, info) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 9999, nombre: 'Administrador visual sintético', rol: 'administrador' } })
    if (path.endsWith('/fuentes/')) return route.fulfill({ json: list([{id: 1, nombre: 'Fuente sintética'}]) })
    if (path.endsWith('/publicaciones/')) return route.fulfill({ json: list([p]) })
    if (path.endsWith('/publicaciones/1/')) return route.fulfill({ json: p })
    if (path.endsWith('/versiones/')) return route.fulfill({ json: list([{ id: 1, numero: 1, creada_en: '2026-10-28T10:00:00Z' }]) })
    if (path.endsWith('/versiones/1/')) return route.fulfill({ json: { numero: 1, estado_extraccion: 'completa', advertencias: ['Revisión documental pendiente'], datos_extraidos: { titulo: { texto_original: '<script>window.ejecucionMaliciosa=true</script>' }, beneficio: { texto_original: 'Beneficio sintético con condiciones no acreditadas.' } } } })
    if (path.endsWith('/documentos/')) return route.fulfill({ json: list([{ id: 1, rol: 'ficha_html', mime: 'text/html', tamano_bytes: 40, sha256: 'a'.repeat(64) }]) })
    if (path.endsWith('/observaciones/')) return route.fulfill({ json: list([{ id: 1, ejecucion_id: 1, version_id: 1, resultado: 'nueva', estado_ejecucion: 'finalizada' }]) })
    if (path.endsWith('/ejecuciones/1/')) return route.fulfill({ json: { id: 1, fuente: p.fuente, estado: 'finalizada', accesos: 6, documentos_distintos: 6, publicaciones_observadas: 0, versiones_nuevas: 0, observaciones_sin_cambios: 0 } })
    return route.fulfill({ json: list([]) })
  })
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/gestion/rastreo')
    await expect(page.getByRole('link', { name: p.titulo })).toBeVisible()
    expect(await page.locator('.crawl-filters').evaluate(el => el.getBoundingClientRect().height)).toBeLessThan(400)
    await expect(page.getByLabel('Buscar título o URL')).toHaveCSS('border-top-width', '1px')
    await page.getByRole('link', { name: p.titulo }).click()
    await expect(page.getByRole('heading', { name: 'Información de la versión 1' })).toBeVisible()
    expect(await page.evaluate(() => window.ejecucionMaliciosa)).toBeUndefined()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.getByText('Datos técnicos', { exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
    await expect(page.getByText('Versión seleccionada', {exact: true})).toBeVisible()
    await expect(page.getByRole('button', {name: 'Anterior', exact: true})).toHaveCount(0)
    const back = page.getByRole('link', {name: 'Volver a publicaciones'})
    await back.focus(); await expect(back).toBeFocused()
    await page.screenshot({ path: info.outputPath(`rastreo-${width}.png`), fullPage: true })
    await page.getByRole('link', { name: 'Consultar ejecución 1' }).click()
    await expect(page.getByText('Fuente sintética · Descarga finalizada')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Incidencias' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})

test('backend real rechaza consulta y descarga anónimas', async ({ request }) => {
  for (const path of ['publicaciones/', 'documentos/1/descarga/']) {
    const response = await request.get(`/api/gestion/rastreo/${path}`)
    expect(response.status()).toBe(403)
  }
})

test('filtros, páginas, versiones, descarga, error y reintento con API simulada', async ({ page }) => {
  let failList = true
  let failDownload = true
  const queries = []
  const execution = { id: 1, fuente: p.fuente, estado: 'finalizada', accesos: 6, documentos_distintos: 6, publicaciones_observadas: 0, versiones_nuevas: 0, observaciones_sin_cambios: 0 }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    expect(route.request().method()).toBe('GET')
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 9999, nombre: 'Admin sintético', rol: 'administrador' } })
    if (path.endsWith('/fuentes/')) return route.fulfill({ json: list([{id: 1, nombre: 'Fuente sintética'}]) })
    if (path.endsWith('/publicaciones/')) {
      queries.push(Object.fromEntries(url.searchParams))
      if (url.searchParams.get('q') === 'vacio') return route.fulfill({ json: list([]) })
      if (url.searchParams.get('q') === 'error' && failList) return route.fulfill({ status: 503, json: {} })
      return route.fulfill({ json: { ...list([{ ...p, titulo: url.searchParams.get('page') === '2' ? 'Segunda página sintética' : p.titulo }]), count: 13 } })
    }
    if (path.endsWith('/publicaciones/1/')) return route.fulfill({ json: p })
    if (path.endsWith('/versiones/')) return route.fulfill({ json: list([{ id: 2, numero: 2 }, { id: 1, numero: 1 }]) })
    if (/\/versiones\/[12]\/$/.test(path)) return route.fulfill({ json: { numero: path.endsWith('/2/') ? 2 : 1, datos_extraidos: { descripcion: path.endsWith('/2/') ? 'Condiciones de versión B' : 'Condiciones de versión A reutilizada' }, advertencias: ['Revisión documental pendiente'] } })
    if (path.endsWith('/documentos/')) return route.fulfill({ json: list([{ id: 8, rol: 'ficha_html', mime: 'text/html', tamano_bytes: 50, sha256: 'b'.repeat(64) }]) })
    if (path.endsWith('/descarga/')) {
      if (failDownload) { failDownload = false; return route.fulfill({ status: 409, json: { detail: 'Evidencia ausente' } }) }
      return route.fulfill({ contentType: 'application/octet-stream', headers: { 'Content-Disposition': 'attachment; filename="evidencia-8.html"' }, body: '<script>window.htmlDescargadoEjecutado=true</script>' })
    }
    if (path.endsWith('/ejecuciones/')) return route.fulfill({ json: list([execution]) })
    if (path.endsWith('/ejecuciones/1/')) return route.fulfill({ json: execution })
    if (path.endsWith('/accesos/')) return route.fulfill({ json: list([{ id: 1, rol: 'ficha', http_status: 200, resultado: 'reutilizado', url_original: 'https://example.org/ficha' }]) })
    if (path.endsWith('/incidencias/')) return route.fulfill({ json: list([{ id: 1, codigo: 'REVISION_DOCUMENTAL_PENDIENTE', gravedad: 'aviso' }]) })
    return route.fulfill({ json: list([]) })
  })
  for (const width of [1440, 390]) {
    failList = true; failDownload = true
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/inicio')
    await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Rastreo', exact: true }).click()
    await expect(page.getByRole('link', { name: p.titulo })).toBeVisible()
    await expect(page.getByRole('button', {name: 'Anterior', exact: true})).toBeDisabled()
    await expect(page.getByRole('button', {name: 'Anterior', exact: true})).toHaveCSS('cursor', 'not-allowed')
    await page.getByRole('button', { name: 'Siguiente', exact: true }).click()
    await expect(page.getByRole('button', {name: 'Siguiente', exact: true})).toBeDisabled()
    await expect(page.getByRole('link', { name: 'Segunda página sintética' })).toBeVisible()
    expect(queries.at(-1).page).toBe('2')
    await page.getByLabel('Fuente', {exact: true}).selectOption('1')
    await page.getByLabel('Buscar título o URL').fill('vacio')
    await page.getByRole('button', { name: 'Buscar', exact: true }).click()
    await expect(page.getByText('No hay registros para esta consulta.')).toBeVisible()
    expect(queries.at(-1)).toEqual({ q: 'vacio', fuente: '1', page: '1' })
    await page.getByLabel('Buscar título o URL').fill('error')
    await page.getByRole('button', { name: 'Buscar', exact: true }).click()
    await expect(page.getByText('BecaNexo no está disponible en este momento. Inténtalo de nuevo más tarde.')).toBeVisible()
    failList = false
    await page.getByRole('button', { name: 'Reintentar', exact: true }).click()
    await page.getByRole('link', { name: p.titulo }).click()
    await expect(page.getByText('Condiciones de versión A reutilizada').first()).toBeVisible()
    await page.getByRole('button', { name: 'Consultar versión 2' }).click()
    await expect(page.getByText('Condiciones de versión B').first()).toBeVisible()
    await page.getByRole('button', { name: 'Descargar evidencia' }).click()
    await expect(page.getByText('Evidencia no disponible o inconsistente.')).toBeVisible()
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Descargar evidencia' }).click()
    expect((await download).suggestedFilename()).toBe('evidencia-8.html')
    expect(await page.evaluate(() => window.htmlDescargadoEjecutado)).toBeUndefined()
    await page.getByRole('link', { name: 'Ejecuciones', exact: true }).click()
    await page.getByRole('link', { name: 'Ejecución 1', exact: true }).click()
    await expect(page.getByText('ficha · HTTP 200 · Documento ya almacenado')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Revisión documental pendiente' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})
