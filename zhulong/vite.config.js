import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import fs from 'fs'

const projectDir = import.meta.dirname

const rootIndexFallback = () => ({
  name: 'root-index-fallback',
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      if (req.url !== '/') {
        next()
        return
      }

      try {
        const indexPath = resolve(projectDir, 'index.html')
        const html = fs.readFileSync(indexPath, 'utf-8')
        const transformed = await server.transformIndexHtml('/', html)
        res.statusCode = 200
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end(transformed)
      } catch (error) {
        next(error)
      }
    })
  }
})

export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [rootIndexFallback(), vue()],
  resolve: {
    alias: {
      '@': resolve(projectDir, 'src')
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        additionalData: `@use "@/styles/variables.scss" as *;`,
        api: 'modern-compiler'
      }
    }
  },
  build: {
    chunkSizeWarningLimit: 600
  },
  server: {
    port: 3000,
    strictPort: true,
    open: false
  }
})
