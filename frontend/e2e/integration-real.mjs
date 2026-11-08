/* global process, console, fetch, setTimeout, URL, document, innerWidth */
import { chromium } from 'playwright'
import { spawn, spawnSync } from 'node:child_process'
import { randomUUID, randomBytes } from 'node:crypto'
import { mkdtempSync, mkdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import net from 'node:net'
import { createServer } from 'vite'
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const root = path.dirname(frontend), python = path.join(root, '.venv/Scripts/python.exe')
const helper = path.join(frontend, 'e2e/integration_server.py')
assert(process.argv.includes('--reset-test-db'), 'Requiere --reset-test-db: borra solo datos de test_becanexo_db; no usar mientras corre otra suite')
process.chdir(frontend)
mkdirSync('test-results', { recursive: true })
const storage = mkdtempSync(path.join(tmpdir(), 'becanexo-validation-'))
const password = randomBytes(32).toString('base64url'), admin = `integration-${randomUUID()}@example.com`
let server, browser, vite
try {
  // Never connect to a pre-existing backend on the isolated port.
  await new Promise((resolve, reject) => {
    const probe = net.createServer()
    probe.once('error', reject)
    probe.listen(8765, '127.0.0.1', () => probe.close(resolve))
  })
  let existing = false
  try {
    const response = await fetch('http://127.0.0.1:5173/src/App.jsx')
    existing = response.ok && (await response.text()).includes('/gestion/rastreo/*')
    assert(existing, '5173 no sirve la aplicacion esperada')
  } catch (error) {
    if (error.code === 'ERR_ASSERTION') throw error
  }
  if (!existing) {
    vite = await createServer({ root: frontend, configFile: path.join(frontend, 'vite.config.js'), server: { host: '127.0.0.1', port: 5173, strictPort: true } })
    await vite.listen()
  }
  const seed = spawnSync(python, [helper, 'seed'], { input: JSON.stringify({ admin, password, storage, reset_test_db: true }), encoding: 'utf8' })
  if (seed.status !== 0) throw Error('Isolated seed failed: ' + seed.stderr)
  const fixture = JSON.parse(seed.stdout.trim())
  server = spawn(python, [helper, 'serve', storage], { stdio: 'ignore' })
  let ready = false
  for (let i = 0; i < 60; i++) { try { if ((await fetch('http://127.0.0.1:8765/api/auth/csrf/')).ok) { ready = true; break } } catch { /* Wait for our backend to bind. */ } await new Promise(r => setTimeout(r, 250)) }
  assert(ready && server.exitCode === null && !server.killed, 'isolated backend readiness')
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage()
  // Transport only: every API response comes from actual Django/PostgreSQL.
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (!u.pathname.startsWith('/api/')) return route.continue()
    u.port = '8765'
    const response = await route.fetch({ url: u.toString() })
    await route.fulfill({ response })
  })
  async function api(url, method = 'GET', data) {
    return page.evaluate(async ({ url, method, data }) => {
      const headers = { 'Content-Type': 'application/json' }
      if (method !== 'GET') headers['X-CSRFToken'] = (await (await fetch('/api/auth/csrf/')).json()).csrfToken
      const r = await fetch(url, { method, headers, body: data === undefined ? undefined : JSON.stringify(data) })
      return { status: r.status, body: r.status === 204 ? null : await r.json() }
    }, { url, method, data })
  }
  async function login(email) {
    await page.goto('http://127.0.0.1:5173/login')
    await page.getByLabel('Correo electrónico').fill(email)
    await page.getByLabel('Contraseña', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click()
    await page.waitForURL('**/inicio')
  }
  await page.goto('http://127.0.0.1:5173/becas')
  assert.equal((await api('/api/becas/')).status, 200)
  assert.equal((await api('/api/perfil/')).status, 403)
  assert.equal((await api('/api/gestion/rastreo/publicaciones/')).status, 403)
  assert.equal((await api('/api/notificaciones/')).status, 403)
  const registered = await api('/api/auth/registro/', 'POST', { nombre: 'Registro sintético aislado', email: `register-${randomUUID()}@example.com`, password, password_confirm: password })
  assert.equal(registered.status, 201)
  await login(fixture.student)
  const notices = await api('/api/notificaciones/')
  assert.equal(notices.status, 200)
  assert(notices.body.count > 0, 'Las publicaciones sintéticas deben generar avisos al postulante coincidente')
  await page.goto('http://127.0.0.1:5173/notificaciones')
  await page.getByRole('heading', { name: 'Notificaciones', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Marcar como leída' }).first().click()
  await page.getByText('Leída', { exact: true }).first().waitFor()
  assert.equal((await api('/api/notificaciones/')).body.no_leidas, notices.body.no_leidas - 1)
  await page.getByRole('link', { name: 'Ver beca' }).first().click()
  await page.waitForURL('**/becas/*')
  const recommendations = await api('/api/becas/recomendaciones/')
  assert.equal(recommendations.status, 200)
  assert(recommendations.body.results.length > 0, 'Recomendaciones sobre ofertas sintéticas públicas')
  console.log('PASS real registration/notifications/read/detail/recommendations on test PostgreSQL')
  await page.goto('http://127.0.0.1:5173/perfil')
  await page.getByLabel('Nombre visible').fill('Persona sintética integración')
  await page.getByLabel('Sobre mi perfil').fill('Intereses declarados de prueba aislada')
  await page.getByRole('button', { name: 'Guardar datos personales' }).click()
  await page.getByText('Cambios guardados.', { exact: true }).waitFor()
  await page.reload()
  assert.equal(await page.getByLabel('Nombre visible').inputValue(), 'Persona sintética integración')
  assert.equal(await page.getByLabel('Sobre mi perfil').inputValue(), 'Intereses declarados de prueba aislada')
  const catalogs = (await api('/api/perfil/catalogos/')).body
  const foreign = catalogs.paises.find(p => p.codigo !== 'EC')
  assert.equal((await api('/api/perfil/', 'PATCH', { nacionalidad: foreign.id })).status, 400)
  assert.equal((await api('/api/perfil/', 'PATCH', { descripcion: 'x'.repeat(1501) })).status, 400)
  const exp = await api('/api/perfil/experiencias/', 'POST', { cargo: 'Prueba integración', fecha_inicio: '2020-01-01', actual: true, fecha_fin: null })
  assert.equal(exp.status, 201)
  assert.equal((await api(`/api/perfil/experiencias/${exp.body.id}/`, 'PATCH', { fecha_fin: '2021-01-01' })).status, 400)
  await page.reload()
  await page.getByRole('button', { name: /Editar experiencia: Prueba integración/ }).click()
  assert(await page.getByLabel('Fecha final', { exact: true }).isDisabled())
  assert.equal(await page.getByLabel('Fecha final', { exact: true }).inputValue(), '')
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
  console.log('PASS real sessions/profile/name/description/nationality/current experience/invalid inputs')
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `profile overflow ${width}`)
    await page.getByLabel('Nombre visible').focus(); await page.keyboard.press('Tab')
    assert(await page.locator('[name="nacionalidad"]').evaluate(e => e === document.activeElement))
    await page.screenshot({ path: `test-results/integration-profile-${width}.png`, fullPage: true })
  }
  await page.goto('http://127.0.0.1:5173/preferencias')
  await page.getByRole('heading', { name: 'Idiomas, preferencias y disponibilidad' }).waitFor()
  assert.equal((await api('/api/perfil/formaciones/')).status, 200)
  assert.equal((await api('/api/perfil/idiomas/')).status, 200)
  assert.equal((await api('/api/perfil/preferencias/')).status, 200)
  assert.equal((await api(`/api/becas/${fixture.offer}/comparacion/`)).status, 200)
  const academicOffer = (await api('/api/becas/')).body.results.find((offer) => offer.titulo.includes('E · Área TIC'))
  assert(academicOffer, 'Falta el escenario académico sintético E')
  await page.goto(`http://127.0.0.1:5173/becas/${academicOffer.id}`)
  await page.getByRole('button', { name: 'Comparar requisitos' }).click()
  await page.getByText(/Se evaluaron tus formaciones declaradas; ninguna cumple conjuntamente/).first().waitFor()
  const comparisonText = await page.locator('.comparison').innerText()
  assert(!comparisonText.includes('academico_E_0') && !comparisonText.includes('Sin dato utilizado'))
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `academic comparison overflow ${width}`)
    await page.locator('.comparison').screenshot({ path: `test-results/integration-comparison-academic-${width}.png` })
  }
  console.log('PASS real academic comparison explanation without internal group IDs at 1440/390/320px')
  await page.goto(`http://127.0.0.1:5173/becas/${fixture.offer}`)
  await page.getByRole('button', { name: 'Guardar en favoritos' }).click()
  await page.getByRole('button', { name: 'Quitar de favoritos' }).waitFor()
  await page.reload(); await page.getByRole('button', { name: 'Quitar de favoritos' }).waitFor()
  await page.goto('http://127.0.0.1:5173/favoritos')
  await page.getByRole('button', { name: 'Quitar de favoritos' }).click()
  assert.equal((await api('/api/gestion/convocatorias/')).status, 403)
  const noCsrf = await page.evaluate(async () => (await fetch('/api/auth/me/', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nombre: 'No permitido' }) })).status)
  assert.equal(noCsrf, 403)
  assert.equal((await api('/api/auth/logout/', 'POST')).status, 204)
  assert.equal((await api('/api/auth/me/')).status, 403)
  console.log('PASS real catalog/favorites/reload/comparison/preferences/role rejection/CSRF/logout')
  await login(admin)
  assert.equal((await api('/api/perfil/')).status, 403)
  assert.equal((await api('/api/notificaciones/')).status, 403)
  await page.goto(`http://127.0.0.1:5173/gestion/convocatorias/${fixture.offer}`)
  await page.getByRole('link', { name: 'Gestionar entidades oferentes' }).waitFor()
  const types = (await api('/api/becas/catalogos/')).body.tipos_requisito
  const created = await api(`/api/gestion/convocatorias/${fixture.offer}/requisitos/`, 'POST', { tipo_requisito: types.find(t => t.codigo === 'DOCUMENTO').id, texto_original: 'Instrucciones sintéticas '.repeat(30), obligatorio: true, activo: true, validado: false, modo_comprobacion: 'entidad_oferente', valor_estructurado: { documento: 'Documento sintético', condiciones: 'Cuando corresponda' } })
  assert.equal(created.status, 201)
  // A real invalid write must preserve the existing record.
  assert.equal((await api(`/api/gestion/convocatorias/${fixture.offer}/requisitos/${created.body.id}/`, 'PATCH', { valor_estructurado: { documento: 'Documento sintético', url_documento: 'javascript:alert(1)' } })).status, 400)
  await page.reload()
  const requirements = page.getByRole('region', { name: 'Requisitos', exact: true })
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    const edit = requirements.getByRole('button', { name: 'Editar', exact: true }).last()
    await edit.focus(); await page.keyboard.press('Enter')
    assert.equal(await requirements.getByLabel('Nombre del documento').inputValue(), 'Documento sintético')
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `editor overflow ${width}`)
    await requirements.screenshot({ path: `test-results/integration-editor-${width}.png` })
    await requirements.getByRole('button', { name: 'Cancelar', exact: true }).click()
  }
  const review = `/api/gestion/rastreo/publicaciones/${fixture.publication}/versiones/${fixture.version}/revisiones/`
  assert.equal((await api(review)).status, 200)
  assert.equal((await api(review, 'POST', { dimension: 'extraccion', decision: 'pendiente', motivo: 'Revisión sintética de integración aislada', evidencia_id: null, sustituye_id: null, clave_accion: randomUUID() })).status, 201)
  await page.goto(`http://127.0.0.1:5173/gestion/rastreo/publicaciones/${fixture.publication}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.getByText('Historial de revisiones', { exact: true }).click()
  await page.getByText('Revisión sintética de integración aislada', { exact: true }).first().waitFor()
  console.log('PASS real administrative documentation/invalid URL/review write+read in isolated PostgreSQL')
} finally {
  if (browser) await browser.close()
  if (server && server.exitCode === null) { const ended = new Promise(r => server.once('exit', r)); server.kill(); await ended }
  if (vite) await vite.close()
  assert(path.dirname(storage) === path.resolve(tmpdir()) && path.basename(storage).startsWith('becanexo-validation-'))
  rmSync(storage, { recursive: true, force: true })
}
