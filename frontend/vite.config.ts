/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// Backend URL is dynamic:
//   - native dev → defaults to localhost:8000
//   - docker dev → set VITE_BACKEND_URL=http://backend:8000 (compose service name)
//   - production → FastAPI serves the SPA itself, no proxy needed
const backendUrl = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: backendUrl, changeOrigin: true },
      '/health': { target: backendUrl, changeOrigin: true },
    },
    watch: {
      // Polling lets HMR work reliably across the docker bind-mount.
      usePolling: true,
      interval: 200,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
