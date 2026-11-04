import { defineConfig, devices } from '@playwright/test';

// Runs against the dev stack: the Otporko API must be up (OTPORNO_API_URL, default http://127.0.0.1:8020)
// and Vite proxies /api to it.
const channel = process.env.PW_CHANNEL || undefined;

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5175',
    trace: 'retain-on-failure',
    locale: 'hr-HR',
    timezoneId: 'Europe/Zagreb',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel } }],
  webServer: {
    command: 'pnpm dev --host 127.0.0.1',
    url: 'http://127.0.0.1:5175',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { OTPORNO_API_URL: process.env.OTPORNO_API_URL ?? 'http://127.0.0.1:8020' },
  },
});
