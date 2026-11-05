/* global process, fetch */
// Own Vite in this process so Windows shell children cannot outlive the run.
import { createServer } from 'vite'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
let vite
try {
  let existing = false
  try {
    const response = await fetch('http://127.0.0.1:5173/src/App.jsx')
    existing = response.ok && (await response.text()).includes('/gestion/rastreo/*')
    if (!existing) throw new Error('El puerto 5173 no corresponde al frontend esperado')
  } catch (error) { if (error.message.includes('puerto 5173')) throw error }
  if (!existing) {
    vite = await createServer({ root: frontend, configFile: path.join(frontend, 'vite.config.js'), server: { host: '127.0.0.1', port: 5173, strictPort: true } })
    await vite.listen()
  }
  const child = spawn(process.execPath, ['node_modules/@playwright/test/cli.js', 'test', '--config=playwright.reviews.config.js', '--output=test-results/reviews-delivery-final'], { cwd: frontend, stdio: 'inherit' })
  process.exitCode = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', code => resolve(code ?? 1)) })
} finally {
  if (vite) await vite.close()
}
