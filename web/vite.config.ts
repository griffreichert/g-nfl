import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // local dev: forward API calls to the FastAPI backend (make api)
      '/api': 'http://localhost:8000',
    },
  },
})
