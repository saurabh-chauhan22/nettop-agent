import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  // During `npm run dev`, the Python API (python ui/api.py) answers /api on port 8000
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
