import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const r = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['favicon.svg', 'robots.txt', 'pwa-icon.svg'],
      manifest: {
        name: 'Flash',
        short_name: 'Flash',
        description: 'Envoyez, payez, épargnez — instantanément.',
        lang: 'fr',
        theme_color: '#8c1d33',
        background_color: '#161619',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        runtimeCaching: [
          {
            // Lecture seule mise en cache pour un mode hors-ligne dégradé (solde, historique).
            urlPattern: ({ url }) =>
              /\/v1\/(wallets|statement|notifications)(\b|\/)/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'flash-read',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 60, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
  resolve: {
    alias: {
      '@': r('./src'),
      '@app': r('./src/app'),
      '@features': r('./src/features'),
      '@shared': r('./src/shared'),
      '@pages': r('./src/pages'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/v1': { target: process.env.VITE_API_PROXY ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    css: true,
    exclude: ['e2e/**', 'node_modules/**'],
  },
});
