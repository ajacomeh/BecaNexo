import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

test('comparación real de tres opciones con fixture DEMOSTRACIÓN', async ({ browser }, testInfo) => {
  const fixture = JSON.parse(execFileSync(resolve('../.venv/Scripts/python.exe'), [resolve('e2e/bootstrap_comparacion.py')], { encoding: 'utf8' }))
  const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } })
  await context.addCookies([{ name: 'sessionid', value: fixture.session, url: 'http://127.0.0.1:5173', httpOnly: true, sameSite: 'Lax' }])
  try {
    const page = await context.newPage()
    const path = `/becas/${fixture.convocatoria}`
    await page.goto(path)
    await expect(page.getByRole('heading', { name: 'DEMOSTRACIÓN · Comparación de requisitos', exact: true })).toBeVisible()
    const region = page.getByRole('region', { name: 'Comparación de requisitos' })
    await region.getByRole('button', { name: 'Comparar requisitos', exact: true }).click()
    await expect(region.locator('.comparison-summary').filter({ hasText: 'Coincide según tus datos declarados' })).toBeVisible()
    await expect(region.locator('.comparison-summary').filter({ hasText: 'No coincide con un requisito obligatorio' })).toBeVisible()
    await expect(region.locator('.comparison-summary').filter({ hasText: 'Pendiente de comprobar' })).toBeVisible()
    await expect(region.getByText('Verificación externa pendiente', { exact: true })).toHaveCount(3)
    const result = await page.request.get(`/api/becas/${fixture.convocatoria}/comparacion/`)
    expect(result.status()).toBe(200)
    expect((await result.json()).opciones.map(o => o.resultado)).toEqual(['cumple', 'no_cumple', 'desconocido'])
    await region.screenshot({ path: testInfo.outputPath('comparison-desktop.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await region.screenshot({ path: testInfo.outputPath('comparison-mobile.png') })
    await page.reload()
    await region.getByRole('button', { name: 'Comparar requisitos', exact: true }).click()
    await expect(region.locator('.comparison-summary').filter({ hasText: 'Coincide según tus datos declarados' })).toBeVisible()
    await region.getByRole('button', { name: 'Actualizar comparación' }).click()
    await expect(region.locator('.comparison-summary').filter({ hasText: 'No coincide con un requisito obligatorio' })).toBeVisible()
  } finally {
    const csrf = await (await context.request.get('/api/auth/csrf/')).json()
    const response = await context.request.post('/api/auth/logout/', { data: {}, headers: { 'X-CSRFToken': csrf.csrfToken } })
    expect(response.status()).toBe(204)
    await context.close()
  }
})
