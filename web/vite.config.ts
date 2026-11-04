import { fileURLToPath, URL } from 'node:url'
import type { ServerResponse } from 'node:http'
import { defineConfig, type ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'

const BACKEND = 'http://127.0.0.1:8765'

/**
 * /api 代理：
 * - changeOrigin 让 Host 变成 127.0.0.1:8765，后端的 Host 校验（防 DNS 重绑定）才会放行。
 * - SSE（text/event-stream）不缓冲、不压缩、不超时，事件逐条透传。
 * - 后端没起时返回结构化 502，前端据此切到演示数据（MOCK）。
 */
const apiProxy: ProxyOptions = {
  target: BACKEND,
  changeOrigin: true,
  ws: false,
  timeout: 0,
  proxyTimeout: 0,
  configure(proxy) {
    proxy.on('proxyReq', (proxyReq, req) => {
      if (req.url?.startsWith('/api/events')) {
        proxyReq.setHeader('accept', 'text/event-stream')
        proxyReq.removeHeader('accept-encoding')
        req.socket.setNoDelay(true)
        req.socket.setTimeout(0)
      }
    })
    proxy.on('proxyRes', (proxyRes) => {
      const type = String(proxyRes.headers['content-type'] ?? '')
      if (type.includes('text/event-stream')) {
        proxyRes.headers['cache-control'] = 'no-cache, no-transform'
        proxyRes.headers['x-accel-buffering'] = 'no'
        delete proxyRes.headers['content-length']
      }
    })
    proxy.on('error', (err, _req, res) => {
      const out = res as ServerResponse
      if (!out || typeof out.writeHead !== 'function' || out.headersSent) return
      out.writeHead(502, { 'content-type': 'application/json; charset=utf-8' })
      out.end(
        JSON.stringify({
          error: {
            code: 'backend_unreachable',
            message: '后端服务未启动或无法连接（127.0.0.1:8765）',
            hint: '在 E:\\IntelBureau 执行 .venv\\Scripts\\python.exe -m bureau serve 后刷新页面',
            detail: err.message,
          },
        }),
      )
    })
  },
}

export default defineConfig({
  base: '/',
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: { '/api': apiProxy },
  },
  preview: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: { '/api': apiProxy },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
    sourcemap: true,
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/[\\/](echarts|zrender|echarts-wordcloud)[\\/]/.test(id)) return 'echarts'
          if (/[\\/](markdown-it|dompurify|entities|linkify-it|mdurl|punycode\.js|uc\.micro)[\\/]/.test(id)) return 'markdown'
          if (/[\\/](@vue|vue|vue-router)[\\/]/.test(id)) return 'vue'
          return undefined
        },
      },
    },
  },
})
