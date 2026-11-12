import { test, expect } from '@playwright/test'

test('recomendaciones y notificaciones compactas sin desbordamiento ni escrituras', async ({ page }) => {
  const user = { id: 999999, nombre: 'Perfil sintético', rol: 'postulante' }
  const offer = (id, title) => ({ id, titulo: title, estado: 'abierta', institucion: { nombre: 'Entidad de demostración' }, opciones: [], beneficios: [], cierre_dia: '2026-11-30' })
  const rows = [
    { convocatoria: offer(2, 'Beca ficticia de ingeniería y estudios tecnológicos con título extenso'), elegibilidad: 'cumple', afinidad: { estado: 'calculada', explicacion: 'Coinciden intereses académicos declarados.' }, preferencias: { declaradas: true, coincidencias: ['destino'] } },
    { convocatoria: offer(3, 'Beca ficticia de otro ámbito'), elegibilidad: 'no_cumple', afinidad: { estado: 'calculada', explicacion: 'Existe afinidad temática, pero falta un requisito obligatorio.' }, preferencias: { declaradas: false, coincidencias: [] } },
  ]
  const notifications = { count: 2, no_leidas: 1, page: 1, page_size: 10, results: [
    { id: 1, convocatoria_id: 2, titulo: 'Beca de demostración (Ficticia)', motivos: ['área académica declarada'], creada_en: '2026-11-11T12:00:00Z', leida_en: null, disponible: true },
    { id: 2, convocatoria_id: 3, titulo: 'Aviso leído', motivos: ['preferencia de destino'], creada_en: '2026-11-10T12:00:00Z', leida_en: '2026-11-11T13:00:00Z', disponible: true },
  ] }
  const writes = []
  await page.route('**/api/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (request.method() !== 'GET') { writes.push(path); return route.abort() }
    if (path === '/api/auth/me/') return route.fulfill({ json: user })
    if (path === '/api/becas/catalogos/') return route.fulfill({ json: { paises: [], niveles: [], modalidades: [], tipos_beca: [] } })
    if (path === '/api/becas/recomendaciones/') return route.fulfill({ json: { results: rows } })
    if (path === '/api/becas/') return route.fulfill({ json: { count: 0, page: 1, page_size: 12, results: [] } })
    if (path === '/api/notificaciones/') return route.fulfill({ json: notifications })
    return route.abort()
  })
  await page.goto('/becas')
  await page.getByRole('button', { name: 'Para ti · IA' }).click()
  await expect(page.getByRole('article')).toHaveCount(2)
  await expect(page.getByText('Becas ordenadas según tus requisitos y afinidad académica.')).toHaveCount(1)
  await expect(page.getByText('La afinidad temática no garantiza elegibilidad ni adjudicación.')).toHaveCount(1)
  await expect(page.getByRole('article').first()).toContainText('Requisitos declarados: coinciden')
  await expect(page.getByRole('article').last()).toContainText('Requisitos: no cumple')
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Recomendaciones a ${width}px`).toBe(true)
    const columns = await page.locator('.offer-grid').evaluate(element => getComputedStyle(element).gridTemplateColumns.split(' ').length)
    expect(columns).toBe(width === 1440 ? 2 : 1)
  }
  await page.goto('/notificaciones')
  await expect(page.locator('.notification-item')).toHaveCount(2)
  await expect(page.locator('.notification-item').first()).toContainText('Sin leer')
  await expect(page.locator('.notification-item').last()).toContainText('Leída')
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Notificaciones a ${width}px`).toBe(true)
    const content = await page.locator('.notification-item').first().locator('.notification-content').boundingBox()
    const actions = await page.locator('.notification-item').first().locator('.notification-actions').boundingBox()
    expect(actions.y, `Acciones debajo del contenido a ${width}px`).toBeGreaterThanOrEqual(content.y + content.height)
  }
  expect(writes).toEqual([])
})
