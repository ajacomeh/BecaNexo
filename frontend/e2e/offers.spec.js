import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

test('administrador publica y edita; postulante consulta la oferta real de demostración', async ({ browser }, testInfo) => {
  test.setTimeout(120000)
  // Sesiones de fixtures sin contraseñas; autenticación por login se prueba en auth.spec.js.
  const sessions = JSON.parse(execFileSync(resolve('../.venv/Scripts/python.exe'), [resolve('e2e/bootstrap_ofertas.py')], { encoding: 'utf8' }))
  const admin = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } })
  const student = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } })
  await admin.addCookies([{ name: 'sessionid', value: sessions.administrador, url: 'http://127.0.0.1:5173', httpOnly: true, sameSite: 'Lax' }])
  await student.addCookies([{ name: 'sessionid', value: sessions.postulante, url: 'http://127.0.0.1:5173', httpOnly: true, sameSite: 'Lax' }])
  const page = await admin.newPage()
  const reader = await student.newPage()
  const title = 'DEMOSTRACIÓN · BecaNexo catálogo local'
  const institution = 'DEMOSTRACIÓN · Entidad ecuatoriana ficticia'
  try {
    await page.goto('/gestion/instituciones')
    const existingInstitution = await page.request.get('/api/gestion/instituciones/', { params: { q: institution } })
    expect(existingInstitution.ok()).toBeTruthy()
    if (!(await existingInstitution.json()).results.some((r) => r.nombre === institution)) {
      await page.getByRole('button', { name: 'Añadir entidad oferente' }).click()
      await page.getByLabel('Nombre oficial').fill(institution)
      await page.getByLabel('Sector').selectOption('privado')
      await page.getByLabel('Web institucional').fill('https://example.org/demostracion')
      await page.getByRole('button', { name: 'Guardar entidad' }).click()
      await expect(page.getByText(institution, { exact: false }).first()).toBeVisible()
    }
    const existing = await page.request.get('/api/gestion/convocatorias/', { params: { q: title } })
    expect(existing.ok()).toBeTruthy()
    let offer = (await existing.json()).results.find((r) => r.titulo === title)
    if (!offer) {
      await page.goto('/gestion/convocatorias/nueva')
      await page.getByLabel('Título', { exact: false }).fill(title)
      await page.getByLabel('Entidad oferente ecuatoriana').selectOption({ label: institution })
      await page.getByLabel('Descripción', { exact: true }).fill('DEMOSTRACIÓN: oferta sintética sin institución real. No admite postulaciones.')
      await page.getByLabel('Enlace oficial', { exact: true }).fill('https://example.org/demostracion-beca')
      await page.getByLabel('Cierre (America/Guayaquil)').fill('2027-11-30T23:59')
      await page.getByRole('button', { name: 'Guardar convocatoria' }).click()
      await expect(page).toHaveURL(/\/gestion\/convocatorias\/\d+$/)
      const id = page.url().split('/').at(-1)
      const created = await page.request.get(`/api/gestion/convocatorias/${id}/`)
      offer = await created.json()
    } else await page.goto(`/gestion/convocatorias/${offer.id}`)
    const options = page.getByRole('region', { name: 'Opciones de estudio' })
    if (!offer.opciones.length) {
      await options.getByRole('button', { name: 'Añadir opciones de estudio' }).click()
      await options.getByLabel('Nivel', { exact: false }).selectOption('maestria')
      await options.getByLabel('Modalidad').selectOption('presencial')
      await options.getByLabel('Programa', { exact: true }).fill('Programa de DEMOSTRACIÓN')
      await options.getByLabel('Ecuador', { exact: true }).check()
      await options.getByLabel('España', { exact: true }).check()
      await options.getByRole('button', { name: 'Guardar opciones de estudio' }).click()
      await expect(options.getByText('maestria / presencial', { exact: true })).toBeVisible()
    }
    const benefits = page.getByRole('region', { name: 'Beneficios', exact: true })
    if (!offer.beneficios.length) {
      await benefits.getByRole('button', { name: 'Añadir beneficios' }).click()
      await benefits.getByLabel('Concepto financiado').fill('Matrícula')
      await benefits.getByLabel('Porcentaje de este concepto').fill('80')
      await benefits.getByRole('button', { name: 'Guardar beneficios' }).click()
      await expect(benefits.getByText('Matrícula', { exact: true })).toBeVisible()
    }
    const requirements = page.getByRole('region', { name: 'Requisitos', exact: true })
    if (!offer.requisitos.length) {
      await requirements.getByRole('button', { name: 'Añadir requisitos' }).click()
      await requirements.getByLabel('Tipo de requisito').selectOption({ label: 'Certificación externa' })
      await requirements.getByLabel('Texto original del requisito').fill('DEMO: certificado de idioma según bases ficticias.')
      await requirements.getByLabel('Certificados admitidos según las bases').fill('Certificado de demostración, sin validez real.')
      await requirements.getByLabel('Transcripción revisada por administrador').selectOption('true')
      await requirements.getByRole('button', { name: 'Guardar requisitos' }).click()
      await expect(requirements.getByText(/Certificación externa: DEMO/)).toBeVisible()
    }
    await page.getByRole('button', { name: 'Validar y publicar' }).click()
    await expect(page.getByText('Convocatoria publicada.', { exact: true })).toBeVisible()
    await reader.goto('/becas')
    await reader.getByLabel('Buscar título, institución o área').fill(title)
    await reader.getByRole('button', { name: 'Aplicar filtros' }).click()
    await reader.getByRole('link', { name: 'Ver detalle' }).click()
    await expect(reader.getByRole('heading', { name: title })).toBeVisible()
    await expect(reader.getByText('80.00 % de Matrícula')).toBeVisible()
    await expect(reader.getByText(/Verificación externa por la entidad oferente/)).toBeVisible()
    await expect(reader.getByText('Ecuador, España')).toBeVisible()
    const changed = 'DEMOSTRACIÓN: descripción corregida y publicada. Sin oferta real ni postulación.'
    await page.getByLabel('Descripción', { exact: true }).fill(changed)
    await page.getByRole('button', { name: 'Guardar convocatoria' }).click()
    await expect(page.getByText('Cambios guardados. Publica de nuevo después de revisar.')).toBeVisible()
    expect((await reader.request.get(`/api/becas/${offer.id}/`)).status()).toBe(404)
    await page.getByRole('button', { name: 'Validar y publicar' }).click()
    await expect(page.getByText('Convocatoria publicada.', { exact: true })).toBeVisible()
    await reader.reload()
    await expect(reader.getByText(changed)).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('admin-desktop.png'), fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: testInfo.outputPath('admin-mobile.png'), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await reader.screenshot({ path: testInfo.outputPath('detail-desktop.png'), fullPage: true })
    await reader.setViewportSize({ width: 390, height: 844 })
    await reader.screenshot({ path: testInfo.outputPath('detail-mobile.png'), fullPage: true })
    expect(await reader.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await reader.goto('/becas')
    await expect(reader.getByRole('heading', { name: 'Catálogo de becas' })).toBeVisible()
    await expect(reader.getByRole('link', { name: 'Ver detalle' }).first()).toBeVisible()
    expect(await reader.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await reader.screenshot({ path: testInfo.outputPath('catalog-mobile.png'), fullPage: true })
    await reader.setViewportSize({ width: 1440, height: 1000 })
    await reader.screenshot({ path: testInfo.outputPath('catalog-desktop.png'), fullPage: true })
  } finally {
    // Invalida solo las sesiones nuevas de estas fixtures.
    for (const context of [admin, student]) {
      const csrf = await context.request.get('/api/auth/csrf/')
      await context.request.post('/api/auth/logout/', { data: {}, headers: { 'X-CSRFToken': (await csrf.json()).csrfToken } })
      await context.close()
    }
  }
})
