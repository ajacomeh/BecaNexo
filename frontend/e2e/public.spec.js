import { test, expect } from '@playwright/test'

test('bienvenida pública en escritorio y móvil, navegación y teclado', async ({ page }, testInfo) => {
  const mutations = []
  page.on('request', request => { if (request.url().includes('/api/') && !['GET', 'HEAD', 'OPTIONS'].includes(request.method())) mutations.push(request.url()) })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Encuentra oportunidades para continuar tus estudios' })).toBeVisible()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Saltar al contenido' })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'BecaNexo, inicio', exact: true })).toBeFocused()
  const nav = page.getByRole('navigation', { name: 'Navegación principal' })
  await nav.getByRole('link', { name: 'Iniciar sesión' }).click()
  await expect(page.getByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
  await page.getByRole('link', { name: 'BecaNexo, volver al inicio' }).click()
  await nav.getByRole('link', { name: 'Crear cuenta' }).click()
  await expect(page.getByLabel('Confirmar contraseña')).toBeVisible()
  await page.getByRole('link', { name: 'BecaNexo, volver al inicio' }).click()
  await nav.getByRole('link', { name: 'Explorar becas' }).click()
  await expect(page.getByRole('heading', { name: 'Catálogo de becas' })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Cómo funciona' })).toBeVisible()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`welcome-${width}.png`), fullPage: true })
  }
  await nav.getByRole('link', { name: 'Iniciar sesión' }).click()
  await expect(page.getByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
  expect(mutations).toEqual([])
})

test('panel y retorno al detalle en navegador con autenticación simulada, sin escrituras al servidor', async ({ page }) => {
  const user = { id: 999999, nombre: 'Prueba de navegación', email: 'navegacion@example.com', rol: 'postulante' }
  let authenticated = false
  let logins = 0
  const writes = []
  // Toda escritura se intercepta. No se crean sesiones ni se actualiza last_login en desarrollo.
  await page.route('**/api/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/auth/me/') return route.fulfill({ status: authenticated ? 200 : 403, json: authenticated ? user : { detail: 'Sin sesión' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'token-simulado' } })
    if (path === '/api/auth/login/' && request.method() === 'POST') {
      authenticated = true
      logins++
      return route.fulfill({ json: { usuario: user, csrfToken: 'token-renovado-simulado' } })
    }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) { writes.push(path); return route.abort() }
    return route.continue()
  })
  await page.goto('/becas')
  await page.getByRole('link', { name: 'Ver detalle' }).first().click()
  const detail = new URL(page.url()).pathname
  await page.getByRole('link', { name: 'Guardar en favoritos' }).click()
  await page.getByLabel('Correo electrónico').fill(user.email)
  await page.getByLabel('Contraseña', { exact: true }).fill('Valor-ficticio-para-prueba')
  await page.getByRole('button', { name: 'Iniciar sesión' }).click()
  await expect(page).toHaveURL(new RegExp(`${detail}$`))
  await expect(page.getByRole('button', { name: 'Guardar en favoritos' })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Iniciar sesión' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Crear cuenta' })).toHaveCount(0)
  await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Mi panel' }).click()
  await expect(page.getByRole('heading', { name: `Hola, ${user.nombre}` })).toBeVisible()
  expect(logins).toBe(1)
  expect(writes).toEqual([])
})

test('consulta pública y acceso al login sin escribir datos', async ({ page }, testInfo) => {
  const mutations = []
  page.on('request', (request) => { if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method()) && request.url().includes('/api/')) mutations.push(request.url()) })
  await page.goto('/becas')
  await expect(page.getByRole('heading', { name: 'Catálogo de becas' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Iniciar sesión' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Crear cuenta' })).toBeVisible()
  await expect(page.getByText('Crear convocatoria', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('article').first()).toBeVisible()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    const overflow = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth,
      elements: [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1 || el.scrollWidth > el.clientWidth + 5).slice(0, 8).map(el => `${el.tagName}.${el.className?.baseVal || el.className}[${el.clientWidth}/${el.scrollWidth}]`) }))
    expect(overflow.width, `Catálogo ${width}px: ${JSON.stringify(overflow.elements)}`).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath(`catalog-viewport-${width}.png`) })
    await page.getByRole('article').first().scrollIntoViewIfNeeded()
    await page.screenshot({ path: testInfo.outputPath(`catalog-card-${width}.png`) })
    await page.screenshot({ path: testInfo.outputPath(`catalog-${width}.png`), fullPage: true })
  }
  const response = await page.request.get('/api/becas/', { params: { page_size: 1 } })
  expect(response.ok()).toBeTruthy()
  const offer = (await response.json()).results[0]
  expect(offer, 'Se necesita al menos una oferta pública existente; no se crean datos.').toBeTruthy()
  await page.getByLabel('Buscar título, institución o área').fill(offer.titulo)
  await page.getByRole('button', { name: 'Aplicar filtros' }).click()
  await page.getByRole('article').filter({ has: page.getByRole('heading', { name: offer.titulo, exact: true }) }).getByRole('link', { name: 'Ver detalle' }).click()
  await expect(page.getByRole('heading', { name: offer.titulo })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Ver convocatoria oficial' })).toHaveAttribute('href', offer.url_oficial)
  await expect(page.getByText('La postulación se realiza en la plataforma de la entidad oferente.')).toBeVisible()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    const overflow = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: innerWidth,
      elements: [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > innerWidth + 1 || el.scrollWidth > el.clientWidth + 5).slice(0, 8).map(el => `${el.tagName}.${el.className?.baseVal || el.className}[${el.clientWidth}/${el.scrollWidth}]`) }))
    expect(overflow.width, `Detalle ${width}px: ${JSON.stringify(overflow.elements)}`).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath(`detail-viewport-${width}.png`) })
    await page.screenshot({ path: testInfo.outputPath(`public-detail-${width}.png`), fullPage: true })
  }
  await page.getByRole('link', { name: 'Guardar en favoritos' }).click()
  await expect(page).toHaveURL(new RegExp(`/login\\?next=%2Fbecas%2F${offer.id}$`))
  await expect(page.getByRole('heading', { name: 'Inicia sesión' })).toBeVisible()
  await page.reload()
  await expect(page).toHaveURL(new RegExp(`/login\\?next=%2Fbecas%2F${offer.id}$`))
  await page.goto('/favoritos')
  await expect(page).toHaveURL(/\/login$/)
  expect(mutations).toEqual([])
})

test('opciones múltiples y apartados consultables en escritorio y móvil sin escrituras', async ({ page, request }, testInfo) => {
  const writes = []
  page.on('request', req => { if (req.url().includes('/api/') && !['GET', 'HEAD', 'OPTIONS'].includes(req.method())) writes.push(req.url()) })
  const catalog = await request.get('/api/becas/', { params: { page_size: 50 } })
  expect(catalog.ok()).toBeTruthy()
  const offer = (await catalog.json()).results.find(item => item.opciones?.length > 1)
  expect(offer, 'Se necesita una convocatoria pública con varias opciones para esta revisión de lectura.').toBeTruthy()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/becas/${offer.id}`)
    const options = page.locator('article.offer-option')
    await expect(options).toHaveCount(offer.opciones.length)
    const first = options.first()
    await first.scrollIntoViewIfNeeded()
    await first.evaluate(element => element.scrollIntoView({ block: 'start' }))
    await page.screenshot({ path: testInfo.outputPath(`option-summary-${width}.png`) })
    const benefits = first.locator('details.offer-disclosure').first()
    const requirements = first.locator('details.offer-disclosure').nth(1)
    const documents = first.locator('details.offer-disclosure').nth(2)
    await expect(benefits).not.toHaveAttribute('open', '')
    await expect(requirements).toHaveAttribute('open', '')
    await benefits.locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(benefits).toHaveAttribute('open', '')
    await documents.locator('summary').focus()
    await page.keyboard.press('Space')
    await expect(documents).toHaveAttribute('open', '')
    await first.scrollIntoViewIfNeeded()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth)
    expect(overflow, `Detalle con varias opciones a ${width}px`).toBeLessThanOrEqual(width)
    await page.screenshot({ path: testInfo.outputPath(`options-${width}.png`) })
  }
  expect(writes).toEqual([])
})
