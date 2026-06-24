import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// This is the FRONTEND ONLY. The Flask backend (app.py) keeps running on
// port 5000 untouched. In dev, Vite proxies API calls to it so the React
// app can be developed standalone with `npm run dev` inside /client.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5000',
      '/start-test': 'http://localhost:5000',
      '/stop-test': 'http://localhost:5000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
