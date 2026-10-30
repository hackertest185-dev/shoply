import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // SPA fallback — serves index.html for every 404 so React Router works
    historyApiFallback: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        'firebase-messaging-sw': fileURLToPath(new URL('./src/firebase-messaging-sw.js', import.meta.url)),
      },
      output: {
        entryFileNames: chunk => chunk.name === 'firebase-messaging-sw'
          ? 'firebase-messaging-sw.js'
          : 'assets/[name]-[hash].js',
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          redux:  ['@reduxjs/toolkit', 'react-redux'],
        },
      },
    },
  },
});
