// Intentionally separate from vite.config.ts — TanStackRouterVite writes routeTree.gen.ts
// during plugin initialization, which breaks test collection. react() and the @ alias
// are re-declared here; keep them in sync if vite.config.ts changes.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
  },
})
