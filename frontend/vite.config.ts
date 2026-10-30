import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    // 브라우저는 /api만 부르고, 백엔드(127.0.0.1:8000)로 넘긴다. Supabase에는 직접 접속하지 않는다.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
