import base from './playwright.config.js'

// Este recorrido solo hace GET; no ejecuta los bootstrap de otros escenarios.
export default {
  ...base,
  testMatch: 'crawling.spec.js',
  webServer: base.webServer.map(server => ({ ...server, reuseExistingServer: true })),
}
