import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: { timeout: 5000 },
  fullyParallel: false,
  retries: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  ],
  // P1-1 fix: 启动后端+前端两个服务
  webServer: [
    {
      command: 'cd .. && uv run uvicorn orbit.api.main:app --host 127.0.0.1 --port 18888',
      port: 18888,
      timeout: 30000,
      reuseExistingServer: true,
    },
    {
      command: 'pnpm dev',
      port: 5173,
      timeout: 15000,
      reuseExistingServer: true,
    },
  ],
})
