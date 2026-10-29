import base from './playwright.config.js'

// Solo interfaz con API simulada; no inicia Django ni escribe sobre desarrollo.
export default { ...base, testMatch: 'reviews.spec.js', webServer: [{ ...base.webServer[1], reuseExistingServer: true }] }
