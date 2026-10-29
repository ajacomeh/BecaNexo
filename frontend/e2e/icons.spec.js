import { test, expect } from '@playwright/test'

const catalogs = { paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], niveles: [], modalidades: [], tipos_beca: [], tipos_requisito: [], idiomas: [], areas: [], dedicaciones: [], estados: [], niveles_idioma: [] }
const offer = { id: 9001, titulo: 'Oferta sintética de iconografía', institucion: { nombre: 'Entidad sintética' }, estado: 'abierta', beneficios: [], requisitos: [], opciones: [], url_oficial: 'https://example.org/beca', descripcion: 'Datos simulados, no guardados.' }
const list = results => ({ count: results.length, page: 1, page_size: 12, results })

for (const role of ['postulante', 'administrador']) test(`iconos y acciones de ${role}, API simulada`, async ({ page }, info) => {
  let finishSave
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me/' && route.request().method() === 'GET') return route.fulfill({ json: { id: 9999, nombre: 'Persona sintética', rol: role } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'token-simulado' } })
    if (route.request().method() === 'PATCH') {
      await new Promise(resolve => { finishSave = resolve })
      return route.fulfill({ status: 400, json: { nombre: ['Error simulado de guardado.'] } })
    }
    if (path.endsWith('/catalogos/')) return route.fulfill({ json: catalogs })
    if (path === '/api/perfil/') return route.fulfill({ json: { perfil: null } })
    if (path.startsWith('/api/perfil/')) return route.fulfill({ json: [] })
    if (path === '/api/becas/9001/') return route.fulfill({ json: offer })
    if (path.endsWith('/comparacion/')) return route.fulfill({ json: { aviso: 'Declaraciones sin acreditación.', opciones: ['cumple', 'no_cumple', 'desconocido'].map((resultado, id) => ({ id, programa: `Opción ${id}`, resultado, resumen: `Estado ${resultado}`, destinos: [], requisitos: [] })) } })
    if (path === '/api/becas/' || path === '/api/gestion/convocatorias/') return route.fulfill({ json: { ...list([offer]), count: 13 } })
    return route.fulfill({ json: list([]) })
  })
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/becas')
    await expect(page.getByRole('heading', { name: 'Catálogo de becas' })).toBeVisible()
    const nav = page.getByRole('navigation', { name: 'Navegación principal' })
    await expect(nav.getByRole('link', { name: role === 'postulante' ? 'Mi perfil académico' : 'Rastreo' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Anterior', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Anterior', exact: true })).toHaveCSS('cursor', 'not-allowed')
    const search = page.getByRole('button', { name: 'Aplicar filtros', exact: true })
    await search.focus()
    await expect(search).toBeFocused()
    await expect(search.locator('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(await page.locator('svg.ui-icon:not([aria-hidden="true"])').count()).toBe(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: info.outputPath(`${role}-${width}.png`), fullPage: true })
    await page.getByRole('button', { name: 'Editar nombre', exact: true }).click()
    await page.getByRole('button', { name: 'Guardar', exact: true }).click()
    const saving = page.getByRole('button', { name: 'Guardando…' })
    await expect(saving).toBeDisabled()
    await expect(saving).toHaveCSS('cursor', 'wait')
    await expect(saving.locator('.ui-icon-loading')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancelar' })).toHaveCSS('cursor', 'not-allowed')
    await expect.poll(() => typeof finishSave).toBe('function')
    finishSave(); finishSave = undefined
    await expect(page.getByRole('alert')).toContainText('Error simulado de guardado.')
    await expect(page.getByRole('button', { name: 'Guardar', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Cancelar' }).click()
    await expect(page.getByRole('button', { name: 'Editar nombre', exact: true })).toBeFocused()
    await page.getByRole('link', { name: 'Ver detalle', exact: true }).click()
    await expect(page.getByRole('link', { name: 'Ir al sitio oficial', exact: true })).toHaveAttribute('href', offer.url_oficial)
    if (role === 'postulante') {
      await page.getByRole('button', { name: 'Comparar requisitos', exact: true }).click()
      await expect(page.getByText('Estado desconocido', { exact: true })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Actualizar comparación', exact: true })).toBeVisible()
      await page.screenshot({ path: info.outputPath(`comparacion-${width}.png`), fullPage: true })
      await nav.getByRole('link', { name: 'Idiomas y preferencias' }).click()
      await expect(page.getByRole('heading', { name: 'Idiomas, preferencias y disponibilidad' })).toBeVisible()
    } else {
      await nav.getByRole('link', { name: 'Entidades oferentes', exact: true }).click()
      await expect(page.getByRole('button', { name: 'Añadir entidad oferente', exact: true })).toBeVisible()
    }
    await expect(page.getByRole('button', { name: 'Cerrar sesión', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  }
})
