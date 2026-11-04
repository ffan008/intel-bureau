import { createApp } from 'vue'
import '@fontsource/orbitron/latin-500.css'
import '@fontsource/orbitron/latin-700.css'
import '@fontsource/rajdhani/latin-500.css'
import '@fontsource/rajdhani/latin-600.css'
import '@fontsource/rajdhani/latin-700.css'
import '@fontsource/jetbrains-mono/latin-400.css'
import '@fontsource/jetbrains-mono/latin-600.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/motion.css'
import './styles/controls.css'
import './styles/widgets.css'
import './styles/page.css'
import './styles/markdown.css'
import './stores/fx'
import App from './App.vue'
import { router } from './router'
import { bootstrap } from './stores/app'

const app = createApp(App)
app.use(router)
app.config.errorHandler = (err, _vm, info) => console.error('[vue]', info, err)
app.mount('#app')
void bootstrap()
