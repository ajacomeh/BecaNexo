import { defineConfig } from 'vite'
import base from './vite.config.js'

// Solo para la revisión manual del bloque 15. Nunca usa el proxy de desarrollo.
export default defineConfig({
  plugins: [
    ...base.plugins,
    {
      name: 'becanexo-options-test-banner',
      transformIndexHtml() {
        return [{ tag: 'div', injectTo: 'body-prepend',
          attrs: { role: 'note', style: 'position:sticky;top:0;z-index:9999;padding:8px;text-align:center;background:#5b1b1b;color:white;font:bold 14px sans-serif' },
          children: 'ENTORNO AISLADO · test_becanexo_db · Datos ficticios' }]
      },
    },
  ],
  server: {
    host: '127.0.0.1', port: 5174, strictPort: true,
    proxy: { '/api': { target: 'http://127.0.0.1:8766', changeOrigin: false } },
  },
})
