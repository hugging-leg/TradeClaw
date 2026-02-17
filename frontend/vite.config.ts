import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api/agent/events': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 需要禁用 proxy 缓冲，否则事件会被攒到连接关闭才一起发送
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // 确保 SSE 响应不被缓冲
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
