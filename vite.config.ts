import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The root app mounts UI files from frontend/src, which has its own
  // node_modules. Force every imported feature package to use the root React.
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
})
