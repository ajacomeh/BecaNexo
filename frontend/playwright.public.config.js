import config from './playwright.config.js'

// Solo el recorrido anónimo de lectura puede reutilizar servidores del desarrollador.
export default {
  ...config,
  testMatch: '**/public.spec.js',
  webServer: config.webServer.map((server) => ({ ...server, reuseExistingServer: true })),
}
