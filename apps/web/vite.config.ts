/// <reference types="vitest/config" />

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  css: {
    preprocessorOptions: {
      // Los parciales de Carbon aún usan if() de Sass; no son código nuestro.
      scss: { quietDeps: true, silenceDeprecations: ['if-function'] },
    },
  },
  build: {
    outDir: '../../src/voz/static',
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        // VOZ_API apunta el proxy a otro VOZ (p. ej. uno de pruebas con datos temporales).
        target: process.env.VOZ_API ?? 'http://127.0.0.1:8765',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Las consultas por rol sobre la app completa son lentas en jsdom.
    testTimeout: 30_000,
    // material-color-utilities es ESM con imports sin extensión: Node plano no los
    // resuelve, así que Vitest lo procesa con Vite (como hace el build).
    server: { deps: { inline: ['@material/material-color-utilities'] } },
  },
})
