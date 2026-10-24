import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'msedge',
    headless: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  webServer: [
    {
      command: '.\\.venv\\Scripts\\python.exe backend\\manage.py runserver 127.0.0.1:8000 --noreload',
      cwd: '..',
      url: 'http://127.0.0.1:8000/api/auth/csrf/',
      reuseExistingServer: false,
      env: { DJANGO_CSRF_TRUSTED_ORIGINS: 'http://127.0.0.1:5173' },
    },
    {
      command: 'npm.cmd run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
    },
  ],
})
