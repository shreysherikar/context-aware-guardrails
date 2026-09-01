import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../web',
    emptyOutDir: false,
  },
  server: {
    proxy: {
      '/guardrail': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/audit': 'http://localhost:8000',
      '/agents': 'http://localhost:8000',
      '/agent': 'http://localhost:8000',
      '/policy': 'http://localhost:8000',
      '/approval': 'http://localhost:8000',
      '/approvals': 'http://localhost:8000',
      '/security': 'http://localhost:8000',
      '/system': 'http://localhost:8000',
      '/requests': 'http://localhost:8000',
      '/rewrite': 'http://localhost:8000',
      '/computer': 'http://localhost:8000',
      '/gxp': 'http://localhost:8000',
    },
  },
});
