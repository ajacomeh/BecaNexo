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
let server, browser, vite, seeded = false
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
  seeded = true
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
  await login(admin)
  await page.goto(`http://127.0.0.1:5173/gestion/rastreo/publicaciones/${fixture.publication}`)
  const open = page.getByRole('button', { name: 'Crear propuesta', exact: true })
  await open.focus(); await page.keyboard.press('Enter')
  await page.getByLabel('Título propuesto').fill('Propuesta sintética con un título extenso para comprobar adaptación y conservación de valores')
  await page.getByRole('button', { name: 'Añadir opciones de estudio', exact: true }).click()
  await page.getByLabel('Programa o mención original').fill('Opción sintética EC')
  await page.getByLabel('Países candidatos de esta opción').selectOption('EC')
  await page.getByRole('button', { name: 'Añadir beneficios', exact: true }).click()
  assert.equal(await page.getByLabel('Ámbito candidato').inputValue(), 'pendiente')
  await page.getByLabel('Tope literal').fill('$3000')
  await page.getByRole('button', { name: 'Añadir requisitos', exact: true }).click()
  await page.getByLabel('Ámbito candidato').last().selectOption('destino')
  await page.getByLabel('Opción candidata').selectOption({ label: 'Opción sintética EC' })
  await page.getByLabel('Destino de la opción').selectOption('EC')
  await page.getByLabel('Cierre literal (sin inventar hora)').fill('25 de octubre de 2026')
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.getByLabel('Título propuesto').focus()
    await page.keyboard.press('Tab')
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `proposal overflow ${width}`)
    await page.locator('.crawl-proposal').screenshot({ path: `test-results/proposal-real-${width}.png` })
  }
  await page.getByRole('button', { name: 'Guardar propuesta', exact: true }).click()
  await page.getByText('Propuesta guardada fuera del catálogo. No se creó una convocatoria.', { exact: true }).waitFor()
  const listPath = `/api/gestion/rastreo/publicaciones/${fixture.publication}/propuesta/`
  let listing = (await api(listPath)).body
  assert.equal(listing.count, 1)
  const first = listing.results[0]
  assert.equal(first.datos.beneficios[0].ambito, 'pendiente')
  assert.equal(first.datos.requisitos[0].destino, 'EC')
  await page.reload()
  await page.getByRole('button', { name: 'Continuar propuesta', exact: true }).click()
  assert.equal(await page.getByLabel('Ámbito candidato').first().inputValue(), 'pendiente')
  assert.equal(await page.getByLabel('Destino de la opción').inputValue(), 'EC')
  const { version_id, observacion_base_id, revisiones, datos, procedencia } = first
  await page.getByLabel('Ámbito candidato').last().selectOption('comun')
  await page.getByRole('button', { name: 'Guardar propuesta', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'El ámbito común no admite' }).waitFor()
  assert.equal(await page.getByLabel('Destino de la opción').inputValue(), 'EC')
  await page.getByLabel('Ámbito candidato').last().selectOption('destino')
  const incoherent = JSON.parse(JSON.stringify(datos))
  incoherent.requisitos[0].destino = 'PE'
  assert.equal((await api(`/api/gestion/rastreo/propuestas/${first.id}/`, 'PATCH', { version_id, observacion_base_id, revisiones, datos: incoherent, procedencia, clave_accion: randomUUID() })).status, 400)
  assert.equal((await api(`/api/gestion/rastreo/propuestas/${first.id}/`, 'PATCH', { version_id, observacion_base_id, revisiones, datos, procedencia, clave_accion: randomUUID() })).status, 200)
  await page.getByLabel('Título propuesto').fill('Texto pendiente conservado tras conflicto')
  await page.getByRole('button', { name: 'Guardar propuesta', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Otra persona' }).waitFor()
  assert.equal(await page.getByLabel('Título propuesto').inputValue(), 'Texto pendiente conservado tras conflicto')
  assert.equal(await page.getByLabel('Ámbito candidato').first().inputValue(), 'pendiente')
  assert.equal(await page.getByLabel('Destino de la opción').inputValue(), 'EC')
  await page.getByRole('button', { name: 'Actualizar contexto conservando valores' }).click()
  await page.getByText(/Contexto actualizado/).waitFor()
  await page.getByRole('button', { name: 'Guardar propuesta', exact: true }).click()
  await page.getByText('Propuesta guardada fuera del catálogo. No se creó una convocatoria.', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Validar propuesta', exact: true }).click()
  await page.getByText(/Validación actual del último snapshot/).waitFor()
  await page.reload()
  await page.getByRole('button', { name: 'Continuar propuesta', exact: true }).click()
  assert.equal(await page.getByLabel('Título propuesto').inputValue(), 'Texto pendiente conservado tras conflicto')
  listing = (await api(listPath)).body
  assert.equal(listing.count, 3)
  assert.equal((await api(`/api/gestion/rastreo/publicaciones/${fixture.publication}/`)).body.convocatoria_id, null)
  if (process.argv.includes('--integrate')) {
    const latest = listing.results[0]
    const docResult = (await api(`/api/gestion/rastreo/publicaciones/${fixture.publication}/versiones/${fixture.version}/documentos/?page_size=50`)).body
    const docs = docResult.results
    assert(docs.length > 0)
    const reviewPath = `/api/gestion/rastreo/publicaciones/${fixture.publication}/versiones/${fixture.version}/revisiones/`
    async function review(dimension, evidenceId = null, additional = {}) {
      const result = await api(reviewPath, 'POST', { dimension, decision: 'aprobada', motivo: 'Revisión sintética aislada', evidencia_id: evidenceId,
        sustituye_id: null, clave_accion: randomUUID(), ...additional })
      assert.equal(result.status, 201, JSON.stringify(result.body)); return result.body.id
    }
    const reviewIds = [await review('extraccion'), await review('oferente', docs[0].evidencia_id,
      { tipo_oferente: 'entidad_ecuatoriana', referencia: 'Encabezado sintético de prueba' })]
    for (const doc of docs) reviewIds.push(await review('documental', doc.evidencia_id))
    const institutions = (await api('/api/gestion/instituciones/')).body.results
    assert(institutions.length > 0)
    const proposalData = { ...latest.datos, institucion: institutions[0].id,
      titulo: 'Integración sintética aislada', descripcion: 'Borrador sintético con respaldo de prueba',
      url_oficial: 'https://example.org/integracion-sintetica' }
    const refs = [...latest.procedencia.filter((r) => !['titulo', 'institucion', 'url_oficial'].includes(r.campo)),
      ...['titulo', 'institucion', 'url_oficial'].map((field) => ({ campo: field, evidencia_id: docs[0].evidencia_id,
        localizador: 'Sección sintética', motivo: 'Transcripción revisada y confirmada' }))]
    const saved = await api(`/api/gestion/rastreo/propuestas/${latest.id}/`, 'PATCH', {
      clave_accion: randomUUID(), version_id: latest.version_id, observacion_base_id: latest.observacion_base_id,
      revisiones: reviewIds, datos: proposalData, procedencia: refs,
    })
    assert.equal(saved.status, 200, JSON.stringify(saved.body))
    assert.equal(saved.body.pendientes.bloqueos.length, 0, JSON.stringify(saved.body.pendientes.bloqueos))
    await page.reload()
    await page.getByRole('button', { name: 'Continuar propuesta', exact: true }).click()
    await page.getByLabel('Correspondencia con la entidad oferente revisada').fill('La entidad sintética corresponde a la evidencia revisada de prueba')
    if (!docs.some((d) => d.rol === 'bases_pdf')) await page.getByLabel('Ausencia real de bases identificadas').fill('No se identificaron bases en la evidencia sintética')
    await page.getByLabel(/Confirmo el contenido seleccionado/).check()
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `confirmation overflow ${width}`)
      await page.locator('.crawl-draft').screenshot({ path: `test-results/integration-confirm-${width}.png` })
    }
    await page.getByRole('button', { name: 'Crear borrador vinculado' }).focus()
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1200)
    if (!page.url().includes('/gestion/convocatorias/')) {
      throw Error('Creación aislada sin navegación: ' + JSON.stringify(await page.getByRole('alert').allTextContents()))
    }
    await page.waitForURL('**/gestion/convocatorias/*')
    const offerId = Number(new URL(page.url()).pathname.split('/').at(-1))
    assert(Number.isInteger(offerId) && offerId > 0)
    await page.getByRole('heading', { name: 'Procedencia del rastreo' }).waitFor()
    const origin = await api(`/api/gestion/rastreo/convocatorias/${offerId}/origen/`)
    assert.equal(origin.status, 200)
    assert.equal(origin.body.publicacion_id, fixture.publication)
    assert.equal((await api(`/api/becas/${offerId}/`)).status, 404)
    assert.equal((await api(`/api/gestion/convocatorias/${offerId}/`)).body.revision, 'pendiente')
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `editor overflow ${width}`)
      await page.locator('.crawl-origin').screenshot({ path: `test-results/integration-origin-${width}.png` })
    }
    console.log('PASS integration: Django/PostgreSQL de pruebas, sesión/CSRF, revisiones sintéticas, confirmación, borrador vinculado, origen privado y catálogo oculto; 1440/390/320 px.')
  } else console.log('PASS proposals: Django real, PostgreSQL test only, session/CSRF, incomplete save, immutable successors, conflict recovery, reload, validation, keyboard, 1440/390/320px. No canonical link.')
} finally {
  if (browser) await browser.close()
  if (server && server.exitCode === null) { const ended = new Promise(r => server.once('exit', r)); server.kill(); await ended }
  if (seeded) {
    const cleanup = spawnSync(python, [helper, 'cleanup', '--test-db-only'], { encoding: 'utf8' })
    if (cleanup.status !== 0) { process.exitCode = 1; console.error('No se pudo limpiar la base aislada; no iniciar otra suite antes de revisarla.') }
  }
  if (vite) await vite.close()
  assert(path.dirname(storage) === path.resolve(tmpdir()) && path.basename(storage).startsWith('becanexo-validation-'))
  rmSync(storage, { recursive: true, force: true })
}
