import { test, expect } from '@playwright/test'

const offer = {
  id: 12, titulo: 'Oferta sintética de comparación', descripcion: 'Condiciones de ejemplo', estado: 'abierta',
  institucion: { nombre: 'Entidad de prueba' }, opciones: [{ id: 1, programa: 'Programa sintético', nivel: 'grado', modalidad: 'virtual', paises: [1] }],
  beneficios: [], requisitos: [], url_oficial: 'https://example.org/oferta', cierre: null, cierre_dia: null,
}
const catalogs = {
  paises: [{ id: 1, codigo: 'EC', nombre: 'Ecuador' }], idiomas: [{ id: 1, codigo: 'en', nombre: 'Inglés' }],
  areas: [], tipos_requisito: [{ id: 1, codigo: 'IDIOMA', nombre: 'Idioma', esquema_valor: { campos: {} } },
    { id: 2, codigo: 'NACIONALIDAD', nombre: 'Nacionalidad' }, { id: 3, codigo: 'DEDICACION', nombre: 'Dedicación' },
    { id: 4, codigo: 'EDAD', nombre: 'Edad' }],
  niveles: [{ valor: 'grado', nombre: 'Grado' }], modalidades: [{ valor: 'virtual', nombre: 'Virtual' }],
  niveles_idioma: [{ valor: 'B2', nombre: 'B2' }], estados: [], dedicaciones: [{ valor: 'completa', nombre: 'Tiempo completo' }],
}
const requirement = (id, type, result, section) => ({
  id, tipo: type, descripcion: `${type} de prueba`, obligatorio: true, ambito: 'comun', resultado: result,
  explicacion: result === 'desconocido' ? 'Falta un dato declarado.' : result === 'no_cumple' ? 'El dato no coincide.' : 'Coincide según datos declarados.',
  dato_declarado: null, condicion_exigida: { valores: {} }, comprobacion_externa: false, seccion_perfil: section,
})

test('resumen, navegación accesible y actualización tras editar un idioma con API simulada', async ({ page }, testInfo) => {
  const languages = []
  const profile = { id: 1, nacionalidad: 1, dedicacion_disponible: 'parcial' }
  let comparisonReads = 0
  await page.route(url => new URL(url).pathname.startsWith('/api/'), async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/me/') return route.fulfill({ json: { id: 90001, nombre: 'Postulante de prueba', email: 'visual@example.com', rol: 'postulante' } })
    if (path === '/api/auth/csrf/') return route.fulfill({ json: { csrfToken: 'simulado' } })
    if (path === '/api/becas/12/') return route.fulfill({ json: offer })
    if (path === '/api/becas/catalogos/' || path === '/api/perfil/catalogos/') return route.fulfill({ json: catalogs })
    if (path === '/api/becas/12/comparacion/') {
      comparisonReads++
      const items = [requirement(1, 'NACIONALIDAD', 'cumple', null), requirement(2, 'IDIOMA', languages.length ? 'cumple' : 'desconocido', languages.length ? null : 'idiomas'),
        { ...requirement(3, 'DEDICACION', 'cumple', null), dato_declarado: { dedicacion: 'completa' }, condicion_exigida: { valores: { valores_admitidos: ['parcial'] } } },
        requirement(4, 'EDAD', 'no_cumple', 'datos-personales')]
      const destination = { pais: 'EC', nombre: 'Ecuador', resultado: 'no_cumple', resumen: 'No coincide con un requisito obligatorio', requisitos: items }
      return route.fulfill({ json: { aviso: 'Comparación orientativa.', criterio_destacada: 'Revisa los requisitos.', opcion_destacada_id: null,
        opciones: [{ id: 1, programa: 'Programa sintético', nivel: 'grado', modalidad: 'virtual', destinos: ['Ecuador'], resultado: 'no_cumple', resumen: destination.resumen,
          requisitos: items, resultados_destino: [destination], verificaciones_externas_pendientes: 0 }] } })
    }
    if (path === '/api/perfil/') return route.fulfill({ json: { perfil: profile } })
    if (path === '/api/perfil/idiomas/') {
      if (route.request().method() === 'POST') {
        const row = { id: 1, ...route.request().postDataJSON() }
        languages.push(row)
        return route.fulfill({ status: 201, json: row })
      }
      return route.fulfill({ json: languages })
    }
    if (path.startsWith('/api/perfil/')) return route.fulfill({ json: [] })
    return route.fulfill({ status: 500, json: { detail: `Ruta no simulada: ${path}` } })
  })

  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 800 })
    await page.goto('/becas/12')
    await page.getByRole('button', { name: 'Comparar requisitos' }).click()
    const summary = page.getByRole('region', { name: 'Resumen superior: Programa sintético · Ecuador' })
    await expect(summary).toContainText('Cumplidos')
    await expect(summary).toContainText('Incumplidos')
    await expect(summary).toContainText('Sin información suficiente')
    await expect(summary.getByRole('list', { name: 'Coincidencias declaradas' })).toContainText('Dedicación')
    await expect(summary.getByRole('list', { name: 'Incumplimientos declarados' })).toContainText('Edad')
    await expect(summary.getByRole('list', { name: 'Información pendiente' })).toContainText('Idioma')
    await expect(page.getByRole('button', { name: 'Actualizar perfil' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Actualizar preferencias' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: testInfo.outputPath(`comparacion-${width}.png`), fullPage: true })
  }
  const update = page.getByRole('link', { name: 'Actualizar idiomas y niveles' })
  await update.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/preferencias#idiomas$/)
  await expect(page.getByRole('heading', { name: 'Idiomas declarados' })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: testInfo.outputPath('perfil-320.png'), fullPage: true })
  await page.getByRole('button', { name: 'Añadir idioma' }).click()
  await page.getByRole('combobox', { name: /^Idioma/ }).selectOption('1')
  await page.getByLabel('Nivel declarado (MCER)').selectOption('B2')
  await page.getByRole('button', { name: 'Guardar idioma' }).click()
  await expect(page.getByText('Cambios guardados.')).toBeVisible()
  await page.goto('/becas/12')
  await page.getByRole('button', { name: 'Comparar requisitos' }).click()
  await expect(page.getByRole('region', { name: 'Resumen superior: Programa sintético · Ecuador' }).getByText('Cumplidos', { exact: true }).locator('..')).toContainText('3')
  await expect(page.getByRole('link', { name: 'Actualizar idiomas y niveles' })).toHaveCount(0)
  expect(comparisonReads).toBe(4)
  await page.getByRole('button', { name: 'Actualizar perfil' }).click()
  await expect(page).toHaveURL(/\/perfil#datos-personales$/)
  await expect(page.getByRole('heading', { name: 'Datos personales y residencia' })).toBeFocused()
  await page.goto('/becas/12')
  await page.getByRole('button', { name: 'Comparar requisitos' }).click()
  await page.getByRole('button', { name: 'Actualizar preferencias' }).click()
  await expect(page).toHaveURL(/\/preferencias#preferencias$/)
  await expect(page.getByRole('heading', { name: 'Preferencias de estudio' })).toBeFocused()
})
