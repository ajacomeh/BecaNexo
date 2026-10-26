import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { test, expect } from '@playwright/test'

test('administrador configura reglas v2 y postulante compara destinos con API real', async ({ browser }, testInfo) => {
  test.setTimeout(120000)
  const fixture = JSON.parse(execFileSync(resolve('../.venv/Scripts/python.exe'), [resolve('e2e/bootstrap_reglas_v2.py')], { encoding: 'utf8' }))
  const contexts = []
  try {
    for (const role of ['administrador', 'postulante']) {
      const context = await browser.newContext({ baseURL: 'http://127.0.0.1:5173', viewport: { width: 1440, height: 1000 } })
      await context.addCookies([{ name: 'sessionid', value: fixture[role], url: 'http://127.0.0.1:5173', httpOnly: true, sameSite: 'Lax' }])
      contexts.push(context)
    }
    const page = await contexts[0].newPage()
    await page.goto(`/gestion/convocatorias/${fixture.convocatoria}`)
    const catalogs = await (await page.request.get('/api/becas/catalogos/')).json()
    const region = page.getByRole('region', { name: 'Requisitos', exact: true })
    async function rule(code, label, configure) {
      const existing = region.locator('.record-list > li').filter({ hasText: label })
      if (await existing.count()) await existing.getByRole('button', { name: 'Editar', exact: true }).click()
      else await region.getByRole('button', { name: 'Añadir requisitos' }).click()
      await region.getByLabel('Tipo de requisito').selectOption(String(catalogs.tipos_requisito.find(t => t.codigo === code).id))
      await region.getByRole('textbox', { name: 'Texto original del requisito', exact: true }).fill(label)
      await region.getByRole('combobox', { name: 'Transcripción revisada por administrador', exact: true }).selectOption('true')
      await configure()
      await region.getByRole('button', { name: 'Guardar requisitos', exact: true }).click()
      await expect(region.getByRole('button', { name: 'Guardar requisitos', exact: true })).toHaveCount(0)
    }
    async function group() {
      await region.getByRole('combobox', { name: 'Relación entre condiciones académicas' }).selectOption('misma_formacion')
      await region.getByLabel('Clave del grupo de misma formación').fill('academico_demo')
    }
    await rule('FORMACION', 'DEMO v2 · Niveles admitidos', async () => {
      await group()
      await region.getByRole('group', { name: 'Niveles admitidos expresamente en las bases' }).getByRole('checkbox', { name: 'grado', exact: true }).check()
      await region.getByRole('combobox', { name: 'Estado exigido', exact: true }).selectOption('concluidos')
      await region.getByRole('combobox', { name: 'Título obtenido', exact: true }).selectOption('true')
    })
    await rule('TITULO_AREA', 'DEMO v2 · Título equivalente', async () => {
      await group()
      await region.getByRole('textbox', { name: 'Títulos admitidos (uno por línea)', exact: true }).fill('Ingeniería de Software')
      if (!await region.getByLabel('Nombre declarado equivalente').count()) await region.getByRole('button', { name: 'Añadir equivalencia' }).click()
      await region.getByLabel('Nombre declarado equivalente').fill('Ing. Software')
      await region.getByLabel('Nombre admitido en las bases').fill('Ingeniería de Software')
      await region.getByLabel('Referencia que respalda la equivalencia').fill('Bases ficticias DEMO, apartado 3')
    })
    await rule('PROMEDIO', 'DEMO v2 · Promedio del mismo título', async () => {
      await group()
      await region.getByRole('spinbutton', { name: 'Promedio mínimo', exact: true }).fill('8')
      await region.getByRole('spinbutton', { name: 'Mínimo de la escala', exact: true }).fill('0')
      await region.getByRole('spinbutton', { name: 'Máximo de la escala', exact: true }).fill('10')
    })
    await rule('TRASLADO', 'DEMO v2 · Presencia obligatoria en España', async () => {
      await region.getByRole('combobox', { name: 'Ámbito (sin declarar = común)', exact: true }).selectOption(String(fixture.opcion))
      await region.getByRole('combobox', { name: 'Destino específico (requiere opción; vacío = todos)', exact: true }).selectOption(String(fixture.espana))
      await region.getByRole('combobox', { name: 'Traslado requerido', exact: true }).selectOption('true')
    })
    await page.getByRole('button', { name: 'Validar y publicar' }).click()
    await expect(page.getByText('Convocatoria publicada.', { exact: true })).toBeVisible()
    const student = await contexts[1].newPage()
    await student.goto(`/becas/${fixture.convocatoria}`)
    const comparison = student.getByRole('region', { name: 'Comparación de requisitos' })
    await comparison.getByRole('button', { name: 'Comparar requisitos', exact: true }).click()
    await expect(comparison.getByText('Ecuador · Coincide según tus datos declarados', { exact: true })).toBeVisible()
    await expect(comparison.getByText('España · No coincide con un requisito obligatorio', { exact: true })).toBeVisible()
    const response = await student.request.get(`/api/becas/${fixture.convocatoria}/comparacion/`)
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data.opciones[0].resultado).toBe('cumple')
    expect(data.opciones[0].resultados_destino.map(d => d.resultado)).toEqual(['cumple', 'no_cumple'])
    await comparison.getByText('España · No coincide con un requisito obligatorio', { exact: true }).click()
    await expect(comparison.getByText('DEMO v2 · Presencia obligatoria en España', { exact: true })).toBeVisible()
    await comparison.screenshot({ path: testInfo.outputPath('rules-desktop.png') })
    await student.setViewportSize({ width: 390, height: 844 })
    expect(await student.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
    await comparison.screenshot({ path: testInfo.outputPath('rules-mobile.png') })
    const audit = await (await page.request.get(`/api/gestion/convocatorias/${fixture.convocatoria}/auditoria/`)).json()
    expect(audit.results.some(e => e.accion === 'publicar')).toBeTruthy()
    expect(audit.results.some(e => e.accion.startsWith('requisitos_'))).toBeTruthy()
  } finally {
    for (const context of contexts) {
      const csrf = await (await context.request.get('/api/auth/csrf/')).json()
      const logout = await context.request.post('/api/auth/logout/', { data: {}, headers: { 'X-CSRFToken': csrf.csrfToken } })
      expect(logout.status()).toBe(204)
      await context.close()
    }
  }
})
