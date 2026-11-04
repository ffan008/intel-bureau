/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" 时强制使用演示数据（npm run dev:mock） */
  readonly VITE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module 'echarts-wordcloud'
