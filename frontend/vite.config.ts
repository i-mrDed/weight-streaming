import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'
import { fileURLToPath } from 'node:url'

// Build output goes INSIDE the python package so `pip install` users get the
// console with zero Node toolchain (spec §11: commit prebuilt dist).
export default defineConfig({
  plugins: [preact()],
  base: '/console/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: fileURLToPath(new URL('../weight_stream/server/static/console', import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks: {
          fonts: [
            '@fontsource-variable/inter',
            '@fontsource-variable/jetbrains-mono',
            '@fontsource-variable/noto-sans-thai',
          ],
        },
      },
    },
  },
  server: {
    port: 5199,
    proxy: {
      '/v1': 'http://127.0.0.1:8765',
      '/health': 'http://127.0.0.1:8765',
    },
  },
})
