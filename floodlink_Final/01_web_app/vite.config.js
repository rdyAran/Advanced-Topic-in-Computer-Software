import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker the API (02) is reachable as http://api:8000; locally as http://localhost:8000
const target = process.env.API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target, changeOrigin: true } } },
})
