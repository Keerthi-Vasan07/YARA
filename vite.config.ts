import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), cesium()],
  server: {
    port: 5847,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/opendap': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
