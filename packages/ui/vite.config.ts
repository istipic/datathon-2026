/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Library build (type-checked by `tsc --noEmit` first) + vitest config.
export default defineConfig({
  plugins: [react()],
  build: {
    lib: { entry: 'src/index.ts', formats: ['es'], fileName: 'index' },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime', 'maplibre-gl', '@tanstack/react-query'],
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // process CSS so `?raw` imports in tokens.test.ts return the real source text
    css: { include: /.+/ },
  },
});
