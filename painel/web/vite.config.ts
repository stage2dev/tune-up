import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Build com base "/" (o painel Python serve o dist na raiz).
// Em desenvolvimento, /api vai para o servidor Python em 127.0.0.1:8787.
export default defineConfig({
  base: '/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    proxy: { '/api': { target: 'http://127.0.0.1:8787', changeOrigin: false } },
  },
  preview: { host: '127.0.0.1' },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
