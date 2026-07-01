import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import monacoPlugin from 'vite-plugin-monaco-editor'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

const monacoEditorPlugin = (monacoPlugin as any).default || monacoPlugin

export default defineConfig({
  plugins: [
    tailwindcss(),
    vue(),
    monacoEditorPlugin({ languageWorkers: ['editorWorkerService', 'typescript', 'json'] }),
  ],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:18888',
      '/ws': { target: 'ws://127.0.0.1:18888', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          'vis': ['vis-network', 'vis-data'],
          'echarts': ['echarts'],
          'monaco': ['monaco-editor'],
        },
      },
    },
  },
})
