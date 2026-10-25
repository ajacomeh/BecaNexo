import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

test('favoritos persisten al recargar y renovar sesión, y se pueden quitar', async ({ browser }, testInfo) => {
  test.setTimeout(60000)
  const sessions = () => JSON.parse(execFileSync(resolve('../.venv/Scripts/python.exe'), [resolve('e2e/bootstrap_ofertas.py')], { encoding: 'utf8' }))
  const contexts = []
  async function fixture() {
    const keys = sessions()
    const student = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } })
    const admin = await browser.newContext({ baseURL: 'http://127.0.0.1:5173' })
    for (const [context, key] of [[student, keys.postulante], [admin, keys.administrador]]) {
      await context.addCookies([{ name: 'sessionid', value: key, url: 'http://127.0.0.1:5173', httpOnly: true, sameSite: 'Lax' }])
      contexts.push(context)
    }
    return student
  }
  let createdFavorite = null
  let activeContext
  try {
    activeContext = await fixture()
    let page = await activeContext.newPage()
    await page.goto('/becas')
    const response = await page.request.get('/api/becas/', { params: { q: 'DEMOSTRACIÓN · BecaNexo catálogo local' } })
    expect(response.ok()).toBeTruthy()
    const offer = (await response.json()).results.find((r) => r.titulo === 'DEMOSTRACIÓN · BecaNexo catálogo local')
    expect(offer, 'Requiere la oferta DEMOSTRACIÓN existente del recorrido de convocatorias.').toBeTruthy()
    expect(offer.favorito_id, 'No quitar un favorito que ya existía antes de esta prueba.').toBeNull()
    await page.getByLabel('Buscar título, institución o área').fill(offer.titulo)
    await page.getByRole('button', { name: 'Aplicar filtros' }).click()
    const card = page.getByRole('article').filter({ has: page.getByRole('heading', { name: offer.titulo }) })
    await card.getByRole('button', { name: 'Guardar en favoritos' }).click()
    await expect(card.getByRole('button', { name: 'Quitar de favoritos' })).toBeVisible()
    createdFavorite = (await (await page.request.get(`/api/becas/${offer.id}/`)).json()).favorito_id
    await page.reload()
    await expect(card.getByRole('button', { name: 'Quitar de favoritos' })).toBeVisible()
    await card.getByRole('link', { name: 'Ver convocatoria' }).click()
    await expect(page.getByRole('button', { name: 'Quitar de favoritos' })).toBeVisible()
    await page.getByRole('link', { name: 'Mis favoritas', exact: true }).click()
    await expect(page.getByRole('heading', { name: offer.titulo })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('favorites-desktop.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath('favorites-mobile.png'), fullPage: true })
    await page.getByRole('button', { name: 'Cerrar sesión' }).click()
    await expect(page).toHaveURL(/\/login$/)
    // Nueva sesión de fixture para el mismo usuario, sin modificar contraseña ni last_login.
    activeContext = await fixture()
    page = await activeContext.newPage()
    await page.goto('/favoritos')
    await expect(page.getByRole('heading', { name: offer.titulo })).toBeVisible()
    await page.getByRole('article').filter({ has: page.getByRole('heading', { name: offer.titulo }) }).getByRole('button', { name: 'Quitar de favoritos' }).click()
    await expect(page.getByRole('heading', { name: offer.titulo })).toHaveCount(0)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Mis becas favoritas' })).toBeVisible()
    expect((await (await page.request.get(`/api/becas/${offer.id}/`)).json()).favorito_id).toBeNull()
    createdFavorite = null
    await page.screenshot({ path: testInfo.outputPath('favorites-empty.png'), fullPage: true })
  } finally {
    if (createdFavorite && activeContext) {
      const csrf = await (await activeContext.request.get('/api/auth/csrf/')).json()
      await activeContext.request.delete(`/api/favoritos/${createdFavorite}/`, { headers: { 'X-CSRFToken': csrf.csrfToken } })
    }
    for (const context of contexts) {
      const csrf = await (await context.request.get('/api/auth/csrf/')).json()
      await context.request.post('/api/auth/logout/', { data: {}, headers: { 'X-CSRFToken': csrf.csrfToken } })
      await context.close()
    }
  }
})
