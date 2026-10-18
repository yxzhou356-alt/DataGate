import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend so the browser talks to one origin.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': loadEnv(mode, '.', 'DATAGATE_').DATAGATE_API_TARGET || 'http://127.0.0.1:8000' },
  },
}))
