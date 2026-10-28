import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Served by the API server under /admin, so it calls /api on the same origin.
export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  server: { port: 5180, proxy: { '/api': 'http://localhost:8787' } }
});
