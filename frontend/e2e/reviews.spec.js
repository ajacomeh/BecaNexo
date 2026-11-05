import { test, expect } from '@playwright/test'

for (const width of [1440, 390, 320]) test(`Revisión administrativa simulada a ${width}px`, async ({ page }, info) => {
  page.on('pageerror', error => console.error(error.message))
  const reviews = []
  let fail = true
  let phase = 'initial', releaseInitial, releaseRefresh, releaseSave
  const initialGate = new Promise(resolve => { releaseInitial = resolve })
  const refreshGate = new Promise(resolve => { releaseRefresh = resolve })
  const saveGate = new Promise(resolve => { releaseSave = resolve })
  const list = results => ({ results, count: results.length, page: 1, page_size: 12 })
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 9999, nombre: 'Administradora sintética', rol: 'administrador' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'simulado' } })
    if (path.endsWith('/revisiones/')) {
      if (request.method() === 'POST') {
        if (fail) { fail = false; await saveGate; phase = 'fail-read'; return route.fulfill({ status: 409, json: { detail: 'Conflicto sintético: consulte el historial.' } }) }
        reviews.push({ ...request.postDataJSON(), id: 19, administrador: { nombre: 'Administradora sintética' }, creada_en: '2026-10-28T12:00:00Z' })
        return route.fulfill({ status: 201, json: reviews.at(-1) })
      }
      // StrictMode puede consultar dos veces al montar: el escenario depende
      // de la acción del usuario, no del número de peticiones de montaje.
      if (phase === 'initial') await initialGate
      if (phase === 'fail-read') { phase = 'refresh'; return route.fulfill({ status: 500, json: { detail: 'Fallo sintético de consulta' } }) }
      if (phase === 'refresh') { await refreshGate; phase = 'ready' }
      return route.fulfill({ json: { ...list(reviews), vigentes: reviews.slice(-1), numero: 1, ultima_observada: false } })
    }
    if (path.endsWith('/publicaciones/1/')) return route.fulfill({ json: { id: 1, titulo: 'Publicación sintética', fuente: { id: 1, nombre: 'Fuente sintética' }, version_observada_id: 7, url_original: 'https://example.org/ficha' } })
    if (path.endsWith('/versiones/')) return route.fulfill({ json: list([{ id: 7, numero: 1 }]) })
    if (path.endsWith('/versiones/7/')) return route.fulfill({ json: { id: 7, numero: 1, estado_extraccion: 'completa', datos_extraidos: {}, advertencias: [] } })
    if (path.endsWith('/documentos/')) return route.fulfill({ json: list([{ id: 31, evidencia_id: 8, rol: 'bases_pdf', mime: 'application/pdf', tamano_bytes: 12, sha256: 'a'.repeat(64) }]) })
    return route.fulfill({ json: list([]) })
  })
  await page.setViewportSize({ width, height: 900 })
  await page.goto('/gestion/rastreo/publicaciones/1')
  await expect(page.getByText('Cargando revisiones…', { exact: true })).toBeVisible()
  releaseInitial()
  await expect(page.getByText(/Evidencia histórica/)).toBeVisible()
  const open = page.getByRole('button', { name: 'Registrar revisión' })
  await open.focus(); await page.keyboard.press('Enter')
  await page.getByLabel('Dimensión', { exact: true }).selectOption('documental')
  await page.getByLabel('Evidencia exacta').selectOption('8')
  const reason = page.getByLabel('Justificación')
  await page.getByRole('button', { name: 'Guardar revisión' }).click()
  expect(await reason.evaluate(input => input.validity.valueMissing)).toBeTruthy()
  expect(reviews).toHaveLength(0)
  await reason.fill('Documento sintético examinado, página 1.')
  await reason.focus(); await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Guardar revisión' })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: info.outputPath(`revision-${width}.png`), fullPage: true })
  await page.getByRole('button', { name: 'Guardar revisión' }).click()
  await expect(page.getByRole('button', { name: 'Guardar revisión' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Guardar revisión' })).toHaveAttribute('aria-busy', 'true')
  await expect(reason).toBeDisabled()
  releaseSave()
  await expect(page.getByRole('alert')).toContainText('Conflicto sintético')
  await expect(reason).toHaveValue('Documento sintético examinado, página 1.')
  await page.locator('.crawl-reviews').screenshot({ path: info.outputPath(`conflicto-${width}.png`) })
  await page.getByRole('button', { name: 'Actualizar historial antes de reintentar' }).click()
  await expect(page.getByRole('alert')).toContainText('BecaNexo no está disponible')
  await expect(reason).toHaveValue('Documento sintético examinado, página 1.')
  await expect(page.getByRole('button', { name: 'Guardar revisión' })).toBeDisabled()
  await page.locator('.crawl-reviews').screenshot({ path: info.outputPath(`error-consulta-${width}.png`) })
  await page.getByRole('button', { name: 'Actualizar historial antes de reintentar' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Cargando revisiones…', { exact: true })).toBeVisible()
  releaseRefresh()
  await expect(page.getByRole('button', { name: 'Guardar revisión' })).toBeEnabled()
  await page.getByRole('button', { name: 'Guardar revisión' }).click()
  await expect(page.getByText(/Revisión guardada/)).toBeVisible()
  expect(reviews).toHaveLength(1)
  expect(reviews[0].evidencia_id).toBe(8)
  await page.getByText('Historial de revisiones', { exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Revisión 19 · Documentación · Pendiente' })).toBeVisible()
  await expect(page.getByText('Documento 31 · bases_pdf · relación 8 · Primera decisión')).toBeVisible()
})
