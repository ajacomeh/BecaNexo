import { test, expect } from '@playwright/test'

for (const rol of ['postulante', 'administrador']) test(`Inicio integrado de ${rol}, API simulada`, async ({ page }, info) => {
  let account = { id: 9999, nombre: 'Persona sintética', rol }
  const mutations = []
  await page.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'simulado' } })
    if (request.method() === 'PATCH' && path === '/api/auth/me/') {
      mutations.push(path)
      account = { ...account, nombre: request.postDataJSON().nombre }
      return route.fulfill({ json: { nombre: account.nombre } })
    }
    if (path === '/api/auth/logout/') { mutations.push(path); return route.fulfill({ status: 204 }) }
    if (path === '/api/auth/me/') return route.fulfill({ json: account })
    return route.fulfill({ json: { count: 0, page: 1, page_size: 12, results: [] } })
  })
  for (const width of [1440, 390, 320]) {
    account = { ...account, nombre: 'María Alejandra de los Ángeles Apellido Compuesto de prueba' }
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/inicio')
    await expect(page.getByRole('heading', { name: `Hola, ${account.nombre}` })).toBeVisible()
    const nav = page.getByRole('navigation', { name: 'Navegación principal' })
    await expect(nav.getByRole('link', { name: 'Inicio', exact: true })).toHaveAttribute('aria-current', 'page')
    const cards = page.getByRole('navigation', { name: 'Accesos de Inicio' }).getByRole('link')
    await expect(cards).toHaveCount(rol === 'postulante' ? 4 : 3)
    await cards.first().focus()
    await page.keyboard.press('Tab')
    await expect(cards.nth(1)).toBeFocused()
    await expect(cards.nth(1)).toHaveCSS('outline-style', 'solid')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`inicio-${rol}-${width}.png`), fullPage: true })
    const pencil = page.getByRole('button', { name: 'Editar nombre', exact: true })
    await expect(pencil).toHaveAttribute('title', 'Editar nombre')
    await expect(pencil).toHaveAttribute('type', 'button')
    await expect(pencil).toHaveText('')
    await expect(pencil.locator('svg')).toHaveAttribute('aria-hidden', 'true')
    const nameBox = await page.locator('.sidebar-name > span').boundingBox()
    const pencilBox = await pencil.boundingBox()
    expect(pencilBox.width).toBeGreaterThanOrEqual(44)
    expect(pencilBox.height).toBeGreaterThanOrEqual(44)
    expect(nameBox.x + nameBox.width).toBeLessThanOrEqual(pencilBox.x)
    const roleBox = await page.locator('.sidebar-account > .capitalize').boundingBox()
    expect(roleBox.y).toBeGreaterThanOrEqual(Math.max(nameBox.y + nameBox.height, pencilBox.y + pencilBox.height))
    await pencil.focus()
    await expect(pencil).toHaveCSS('outline-style', 'solid')
    await page.keyboard.press('Enter')
    await page.getByLabel('Nombre visible', { exact: true }).fill('Cambio cancelado')
    const before = mutations.length
    await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
    expect(mutations.length).toBe(before)
    await expect(page.getByRole('button', { name: 'Editar nombre', exact: true })).toBeFocused()
    await page.getByRole('button', { name: 'Editar nombre', exact: true }).click()
    await page.getByLabel('Nombre visible', { exact: true }).fill(`Nombre sintético ${width}`)
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()
    await expect(page.getByRole('heading', { name: `Hola, Nombre sintético ${width}` })).toBeVisible()
    await expect(page.locator('.sidebar-name')).toContainText(`Nombre sintético ${width}`)
    await page.reload()
    await expect(page.getByRole('heading', { name: `Hola, Nombre sintético ${width}` })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cerrar sesión', exact: true })).toHaveCount(1)
    await page.getByRole('button', { name: 'Cerrar sesión', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Inicia sesión', exact: true })).toBeVisible()
  }
})

test('visitante real: Inicio protegido y bienvenida pública', async ({ page }) => {
  await page.goto('/inicio')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Inicia sesión', exact: true })).toBeVisible()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Encuentra oportunidades para continuar tus estudios' })).toBeVisible()
})
