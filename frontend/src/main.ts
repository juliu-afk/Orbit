import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'  // WHY 保留——el-drawer 组件需要基础 CSS，style.css 覆盖视觉样式
import App from './App.vue'
import router from './router'
import './style.css'  // 必须在 element-plus CSS 之后——用 Tailwind tokens 覆盖 Element Plus 视觉

// WHY 保留 ElementPlus 全局注册但不使用其组件:
// Step 10 UI 翻新后，仅 el-drawer 用作 DAG/Chart/Search 浮层容器。
// 所有其他 Element Plus 组件（el-button/el-card/el-table 等）不再使用。
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
