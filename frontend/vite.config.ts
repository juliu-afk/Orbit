import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import monacoPlugin from 'vite-plugin-monaco-editor'
import { resolve } from 'path'

const monacoEditorPlugin = (monacoPlugin as any).default || monacoPlugin

export default defineConfig({
  plugins: [
    vue(),
    monacoEditorPlugin({ languageWorkers: ['editorWorkerService', 'typescript', 'json'] }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:18888',
      '/ws': {
        target: 'ws://127.0.0.1:18888',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // WHY chunk 策略：vis-network 和 echarts 体积大，
    // 拆分到独立 chunk 避免首屏加载全部 vendor
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
