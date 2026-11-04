import { defineConfig, devices } from '@playwright/test';

// Runs against the dev stack: the NabavaRadar API must be up (NABAVARADAR_API_URL, default
// http://127.0.0.1:8000) with ingested data; Vite proxies /api to it. Use PW_CHANNEL=msedge to use an
// installed Edge instead of the downloaded Chromium.
const channel = process.env.PW_CHANNEL || undefined;

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    locale: 'hr-HR',
    timezoneId: 'Europe/Zagreb',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel } }],
  webServer: {
    command: 'pnpm dev --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { NABAVARADAR_API_URL: process.env.NABAVARADAR_API_URL ?? 'http://127.0.0.1:8000' },
  },
});
