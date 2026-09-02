import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './styles/global.scss'

const app = createApp(App)

app.use(createPinia())
app.use(router)

router.isReady()
  .then(() => {
    app.mount('#app')
  })
  .catch((error) => {
    console.error('[startup] Initial route failed to load:', error)
    const root = document.querySelector('#app')
    if (root) {
      root.innerHTML = `
        <main class="boot-error" role="alert">
          <strong>页面加载失败</strong>
          <span>请关闭启动窗口后重新运行 start.bat</span>
        </main>
      `
    }
  })
