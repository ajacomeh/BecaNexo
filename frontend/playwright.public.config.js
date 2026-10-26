import config from './playwright.config.js'

// Solo recorridos de lectura o con autenticación interceptada, sin escrituras al servidor.
export default {
  ...config,
  testMatch: '**/public.spec.js',
  webServer: config.webServer.map((server) => ({ ...server, reuseExistingServer: true })),
}
