import base from './playwright.config.js'

// API simulada: ningún GET o POST del recorrido llega a desarrollo.
export default { ...base, testMatch: 'comparison-profile.spec.js',
  webServer: [{ ...base.webServer[1], reuseExistingServer: true }] }
