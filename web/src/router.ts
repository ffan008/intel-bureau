import { createRouter, createWebHistory, type RouteComponent, type RouteRecordRaw } from 'vue-router'
import type { IconName } from './components/icons'

export interface NavItem { path: string; title: string; code: string; icon: IconName }

export const NAV: NavItem[] = [
  { path: '/', title: '作战大屏', code: 'COMMAND DECK', icon: 'screen' },
  { path: '/reports', title: '情报档案', code: 'ARCHIVE', icon: 'reports' },
  { path: '/kb', title: '知识库', code: 'KNOWLEDGE BASE', icon: 'book' },
  { path: '/sources', title: '情报源', code: 'SOURCES', icon: 'sources' },
  { path: '/schedules', title: '调度中心', code: 'SCHEDULER', icon: 'schedules' },
  { path: '/channels', title: '推送通道', code: 'CHANNELS', icon: 'channels' },
  { path: '/agents', title: '智能体', code: 'AGENTS', icon: 'agents' },
  { path: '/system', title: '系统', code: 'SYSTEM', icon: 'system' },
]

declare module 'vue-router' {
  interface RouteMeta { title: string; code: string; shell: boolean }
}

const page = (path: string, load: () => Promise<RouteComponent | { default: RouteComponent }>): RouteRecordRaw => {
  const n = NAV.find((x) => x.path === path)!
  return { path, component: load, meta: { title: n.title, code: n.code, shell: path !== '/' } }
}

const routes: RouteRecordRaw[] = [
  page('/', () => import('./views/ScreenView.vue')),
  page('/reports', () => import('./views/ReportsView.vue')),
  page('/kb', () => import('./views/KbView.vue')),
  page('/sources', () => import('./views/SourcesView.vue')),
  page('/schedules', () => import('./views/SchedulesView.vue')),
  page('/channels', () => import('./views/ChannelsView.vue')),
  page('/agents', () => import('./views/AgentsView.vue')),
  page('/system', () => import('./views/SystemView.vue')),
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  history: createWebHistory('/'),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 情报局` : '情报局 · INTEL BUREAU'
})
