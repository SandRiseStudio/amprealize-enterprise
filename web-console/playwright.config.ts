import { defineConfig, devices } from '@playwright/test';

// Smoke-only Playwright config. The full test matrix still lives in vitest;
// this file exists so the deploy workflow can run post-deploy checks against
// production (or a preview URL) without pulling in a dev server.
//
// Invoke:  npx playwright test
// or:     SMOKE_BASE_URL=https://amprealize.ai npx playwright test tests/smoke

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
