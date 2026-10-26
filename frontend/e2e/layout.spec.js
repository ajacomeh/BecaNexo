import { test, expect } from '@playwright/test'

// Fixtures locales interceptadas: ninguna solicitud llega a la base de datos.
const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], areas: [], idiomas: [], tipos_beca: [], tipos_requisito: [], niveles: [], modalidades: [] }
const offers = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, titulo: `Prueba visual ${i + 1}`, estado: 'abierta', institucion: { nombre: 'Entidad ficticia' }, beneficios: [], opciones: [{ nivel: 'grado', modalidad: 'virtual' }] }))

async function fixtures(page, role) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me/') return route.fulfill({ status: role ? 200 : 403, json: role ? { id: 99999, nombre: 'Persona de prueba visual', rol: role, email: 'visual@example.com' } : {} })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'simulado' } })
    if (path === '/api/auth/logout/') return route.fulfill({ status: 204 })
    if (path === '/api/becas/catalogos/') return route.fulfill({ json: catalogs })
    const results = path.includes('instituciones') ? offers.map(o => ({ id: o.id, nombre: o.titulo, sector: 'publico' })) : path.includes('favoritos') ? offers.map(o => ({ id: o.id, disponible: true, convocatoria: { ...o, institucion: 'Entidad ficticia' } })) : offers
    return route.fulfill({ json: { results, count: 24, page_size: 12, page: Number(url.searchParams.get('page') || 1) } })
  })
}

async function noOverflow(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
}

for (const role of [null, 'postulante', 'administrador']) {
  test(`layout ${role || 'visitante'}: tamaños, desplazamiento y acciones`, async ({ page }, info) => {
    await fixtures(page, role)
    for (const [width, height] of [[1440, 900], [1366, 768], [390, 844], [320, 700]]) {
      await page.setViewportSize({ width, height })
      await page.goto(role === 'administrador' ? '/gestion/convocatorias' : '/becas')
      await expect(page.locator('.offer-card')).toHaveCount(12)
      await noOverflow(page)
      const actions = page.locator(role === 'administrador' ? '.page-heading .heading-actions' : '.public-topbar .heading-actions')
      if (role !== 'postulante') {
        const boxes = await actions.locator('a').evaluateAll(links => links.map(a => { const r = a.getBoundingClientRect(); return { y: r.y, height: r.height } }))
        if (width > 950) expect(Math.abs(boxes[0].y - boxes[1].y)).toBeLessThan(1)
        expect(Math.abs(boxes[0].height - boxes[1].height)).toBeLessThan(1)
      }
      await page.screenshot({ path: info.outputPath(`${width}-inicio.png`) })
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
      expect(await page.evaluate(() => scrollY)).toBeGreaterThan(100)
      if (role && width > 950) {
        const logout = page.getByRole('button', { name: 'Cerrar sesión' })
        await expect(logout).toBeInViewport()
        await logout.focus()
        await expect(logout).toBeFocused()
        expect(Math.abs(await page.locator('.profile-sidebar').evaluate(el => el.getBoundingClientRect().top))).toBeLessThan(1)
      }
      await page.screenshot({ path: info.outputPath(`${width}-final.png`) })
      const pagination = page.getByRole('navigation', { name: 'Paginación', exact: true })
      await pagination.getByRole('button', { name: 'Siguiente' }).click()
      await expect(pagination).toContainText('Página 2')
      await expect(pagination.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
      await pagination.getByRole('button', { name: 'Anterior' }).click()
      await expect(page).toHaveURL(/page=1/)
      await expect(pagination).toContainText('Página 1')
      await page.getByLabel('Buscar título, institución o área').fill('visual')
      await expect(page.getByLabel('Buscar título, institución o área')).toHaveValue('visual')
      await page.getByRole('button', { name: 'Aplicar filtros' }).click()
      await expect(page).toHaveURL(/q=visual/)
      await noOverflow(page)
    }
    if (role === 'administrador') {
      await page.goto('/gestion/instituciones')
      const add = page.getByRole('button', { name: 'Añadir entidad oferente' })
      await expect(add).toBeVisible()
      expect(await add.evaluate(el => Boolean(el.closest('section').querySelector('.record-list').compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING))).toBeTruthy()
      await noOverflow(page)
      await page.screenshot({ path: info.outputPath('instituciones-mobile.png'), fullPage: true })
      await add.click()
      await expect(page.getByRole('heading', { name: 'Nueva entidad oferente' })).toBeVisible()
      await page.getByRole('button', { name: 'Cancelar' }).click()
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.screenshot({ path: info.outputPath('instituciones-desktop.png') })
    }
    if (role === 'postulante') {
      await page.goto('/favoritos')
      await expect(page.locator('.offer-card')).toHaveCount(12)
      await noOverflow(page)
      await page.getByRole('button', { name: 'Siguiente' }).click()
      await expect(page.locator('.pagination')).toContainText('Página 2')
    }
    if (!role) {
      await page.goto('/becas')
      await page.getByRole('link', { name: 'Iniciar sesión' }).click()
      await expect(page).toHaveURL(/\/login$/)
      await page.goto('/becas')
      await page.getByRole('link', { name: 'Crear cuenta' }).click()
      await expect(page).toHaveURL(/\/registro$/)
    }
  })
}

test('menú con altura reducida y reflujo equivalente a zoom 200 %', async ({ page }, info) => {
  await fixtures(page, 'postulante')
  await page.setViewportSize({ width: 1366, height: 400 })
  await page.goto('/becas')
  await expect(page.locator('.offer-card')).toHaveCount(12)
  const nav = page.locator('.profile-sidebar nav')
  expect(await nav.evaluate(el => el.scrollHeight > el.clientHeight)).toBeTruthy()
  await nav.getByRole('link', { name: 'Mis favoritas' }).focus()
  await expect(nav.getByRole('link', { name: 'Mis favoritas' })).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeInViewport()
  await page.screenshot({ path: info.outputPath('altura-reducida.png') })
  // Mitad del viewport CSS de 1440x900: verifica reflujo, no sustituye el control de zoom nativo.
  await page.setViewportSize({ width: 720, height: 450 })
  await noOverflow(page)
  await page.getByRole('button', { name: 'Cerrar sesión' }).focus()
  await expect(page.getByRole('button', { name: 'Cerrar sesión' })).toBeInViewport()
  await page.screenshot({ path: info.outputPath('reflujo-720.png') })
})
