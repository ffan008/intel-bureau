import type { ConfigField, Health, Platform, PlatformDTO } from '@/api/types'

const f = (key: string, label: string, type: ConfigField['type'], extra: Partial<ConfigField> = {}): ConfigField => ({ key, label, type, ...extra })
const fileImport = (p: string) => ({
  key: `${p}.file_import`, label: '文件导入（导出文件 / 粘贴文本）', config_schema: [
    f('inbox_dir', '收件箱目录', 'text', { default: `data/inbox/${p}`, help: '把导出文件放进这个目录，下次运行自动导入' }),
    f('watch', '自动监视目录', 'bool', { default: true }),
  ],
})

export const ADAPTERS: Record<Exclude<Platform, 'demo'>, PlatformDTO['adapters']> = {
  wechat: [
    { key: 'wechat.wda', label: 'WeChatDataAnalysis（本地 API）', config_schema: [
      f('base_url', '服务地址', 'url', { required: true, default: 'http://127.0.0.1:10392' }),
      f('account', '微信账号', 'text', { placeholder: 'wxid_…（留空自动选择第一个）' }),
      f('page_size', '每页条数', 'number', { default: 200 }),
    ] },
    { key: 'wechat.weflow', label: 'WeFlow HTTP API', config_schema: [
      f('base_url', '服务地址', 'url', { required: true, default: 'http://127.0.0.1:5031' }),
      f('token', '访问令牌', 'secret', { required: true }),
    ] },
    fileImport('wechat'),
  ],
  qq: [
    { key: 'qq.onebot', label: 'NapCatQQ（OneBot 11）', config_schema: [
      f('base_url', 'HTTP 服务地址', 'url', { required: true, default: 'http://127.0.0.1:3010' }),
      f('access_token', 'Access Token', 'secret'),
      f('realtime', '接收实时上报', 'bool', { default: true, help: '在 NapCat WebUI 里把 HTTP 上报地址设为 http://127.0.0.1:8765/api/ingest/onebot' }),
      f('report_secret', '上报签名密钥', 'secret', { help: '与 NapCat 上报设置里的 secret 一致，用于校验 X-Signature' }),
    ] },
    fileImport('qq'),
  ],
  feishu: [
    { key: 'feishu.lark_cli', label: '飞书官方 CLI（lark-cli）', config_schema: [
      f('identity', '读取身份', 'select', { default: 'user', options: [{ value: 'user', label: '用户身份（可读所在全部群）' }, { value: 'bot', label: '机器人身份（只读机器人所在群）' }] }),
      f('cli_path', 'lark-cli 路径', 'text', { placeholder: '留空则从 PATH 查找' }),
      f('page_size', '每页条数', 'number', { default: 50 }),
    ] },
    fileImport('feishu'),
  ],
}

export interface PlatformState { enabled: boolean; adapter: string; health: Health; detail: string; hint?: string; checkedMinAgo: number; collectedMinAgo: number }

export const PLATFORM_STATE: Record<Exclude<Platform, 'demo'>, PlatformState> = {
  wechat: { enabled: true, adapter: 'wechat.wda', health: 'ok', detail: 'WeChatDataAnalysis v1.9.2 已连接，账号 wxid_••••8k2', checkedMinAgo: 2, collectedMinAgo: 186 },
  qq: { enabled: true, adapter: 'qq.onebot', health: 'ok', detail: 'NapCat v4.18.41 在线（情报员小号 ••••3302），实时上报已开启', checkedMinAgo: 1, collectedMinAgo: 3 },
  feishu: {
    enabled: true, adapter: 'feishu.lark_cli', health: 'degraded',
    detail: '机器人身份可用；用户身份令牌已于 2026-10-13 过期，只能读取机器人所在的群',
    hint: '在终端执行 lark-cli auth login 重新登录用户身份', checkedMinAgo: 4, collectedMinAgo: 186,
  },
}

export const PLATFORM_LABEL: Record<Platform, string> = { wechat: '微信', qq: 'QQ', feishu: '飞书', demo: '演示' }
