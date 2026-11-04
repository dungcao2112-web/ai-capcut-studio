import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Agy Local Server (server/index.mjs) chạy ở cổng 3001 trên máy Chủ tịch.
// Khi chạy trên Cloud không có server, các request /api sẽ lỗi → Frontend tự fallback sang Demo.
const API_TARGET = process.env.AGY_API ?? 'http://localhost:3001';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  preview: {
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
    },
  },
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 1200,
  },
});
