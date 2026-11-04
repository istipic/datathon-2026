/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Dev: the API runs on :8020 (override with OTPORNO_API_URL); in production Caddy proxies
// /api and /health to the otporno-api service.
export default defineConfig(({ mode }) => {
  const api = loadEnv(mode, '.', '').OTPORNO_API_URL ?? 'http://127.0.0.1:8020';
  return {
    plugins: [react()],
    server: { port: 5175, proxy: { '/api': api, '/health': api } },
    preview: { port: 4175, proxy: { '/api': api, '/health': api } },
    build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
      setupFiles: ['./src/test-setup.ts'],
      css: { include: /.+/ },
    },
  };
});
