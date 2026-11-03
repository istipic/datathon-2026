/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Dev: the API runs on :8000 (override with BLIZU_API_URL); in production Caddy proxies
// /api and /health to the blizu-api service.
export default defineConfig(({ mode }) => {
  const api = loadEnv(mode, '.', '').BLIZU_API_URL ?? 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { '/api': api, '/health': api } },
    preview: { port: 4173, proxy: { '/api': api, '/health': api } },
    build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.test.{ts,tsx}'],
      css: { include: /.+/ },
    },
  };
});
