import config from './playwright.config.js'

// Reutiliza servidores locales y ejecuta solo la fixture DEMOSTRACIÓN de comparación.
export default {
  ...config,
  testMatch: ['**/comparison.spec.js', '**/rules.spec.js'],
  webServer: config.webServer.map(server => ({ ...server, reuseExistingServer: true })),
}
