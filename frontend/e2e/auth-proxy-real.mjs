/* global process, console, fetch, setTimeout */
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { chromium } from 'playwright'
import { createServer } from 'vite'
import config from '../vite.config.js'

const root = path.resolve('..')
const python = path.join(root, '.venv/Scripts/python.exe')
const helper = path.join(process.cwd(), 'e2e/integration_server.py')
const storage = mkdtempSync(path.join(tmpdir(), 'becanexo-validation-'))
const password = randomBytes(32).toString('base64url')
const admin = `logout-${randomUUID()}@example.com`
let backend, vite, browser, seeded = false

try {
  // El puerto aislado no figura en los orígenes de confianza del helper.
  assert.equal(config.server.proxy['/api'].changeOrigin, false)
  const seed = spawnSync(python, [helper, 'seed'], {
    input: JSON.stringify({ admin, password, storage, reset_test_db: true }), encoding: 'utf8',
  })
  assert.equal(seed.status, 0, 'No se pudo preparar test_becanexo_db')
  seeded = true
  const fixture = JSON.parse(seed.stdout.trim())
  backend = spawn(python, [helper, 'serve', storage], { stdio: 'ignore' })
  let ready = false
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      if ((await fetch('http://127.0.0.1:8765/api/auth/csrf/')).ok) { ready = true; break }
    } catch { /* Esperar solo al servidor aislado propio. */ }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  assert(ready, 'El backend aislado no respondió')
  vite = await createServer({
    root: process.cwd(), configFile: false, plugins: config.plugins,
    server: {
      ...config.server, port: 5174, strictPort: true,
      proxy: { '/api': { ...config.server.proxy['/api'], target: 'http://127.0.0.1:8765' } },
    },
  })
  await vite.listen()
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const page = await browser.newPage()
  const base = 'http://127.0.0.1:5174'

  async function signIn(email) {
    await page.goto(`${base}/login`)
    await page.getByLabel(/Correo electr/).fill(email)
    await page.getByLabel(/Contrase/).fill(password)
    await page.getByRole('button', { name: /Iniciar sesi/ }).click()
    await page.waitForURL('**/inicio')
  }

  await signIn(fixture.student)
  await page.getByRole('button', { name: /Cerrar sesi/ }).click()
  await page.waitForURL('**/login')
  await signIn(admin)
  await page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', { name: 'Rastreo' }).waitFor()

  // Simula una sesión terminada en el servidor mientras React aún muestra la cuenta.
  const serverLogout = await page.evaluate(async () => {
    const csrf = await (await fetch('/api/auth/csrf/')).json()
    return (await fetch('/api/auth/logout/', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.csrfToken },
      body: '{}',
    })).status
  })
  assert.equal(serverLogout, 204)
  await page.getByRole('button', { name: /Cerrar sesi/ }).click()
  await page.waitForURL('**/login')
  console.log('PASS: proxy real hacia PostgreSQL de pruebas; logout, segunda cuenta y sesión terminada; CSRF activo.')
} finally {
  if (browser) await browser.close()
  if (vite) await vite.close()
  if (backend && backend.exitCode === null) {
    const ended = new Promise(resolve => backend.once('exit', resolve))
    backend.kill()
    await ended
  }
  if (seeded) {
    const cleanup = spawnSync(python, [helper, 'cleanup', '--test-db-only'], { encoding: 'utf8' })
    if (cleanup.status !== 0) { process.exitCode = 1; console.error('No se pudo limpiar test_becanexo_db') }
  }
  rmSync(storage, { recursive: true, force: true })
}
