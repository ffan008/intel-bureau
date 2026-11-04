import type { ChannelDTO, ChannelKindDTO, ConfigField } from '@/api/types'

const f = (key: string, label: string, type: ConfigField['type'], extra: Partial<ConfigField> = {}): ConfigField => ({ key, label, type, ...extra })

export const CHANNEL_KINDS: ChannelKindDTO[] = [
  { kind: 'feishu_webhook', label: '飞书群机器人（Webhook）', platform_label: '飞书', config_schema: [
    f('webhook_url', 'Webhook 地址', 'secret', { required: true, placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/…', help: '群设置 → 群机器人 → 添加自定义机器人' }),
    f('sign_secret', '签名校验密钥', 'secret', { help: '机器人安全设置里开启「签名校验」后填写' }),
    f('card_style', '卡片样式', 'select', { default: 'card', options: [{ value: 'card', label: '交互卡片' }, { value: 'text', label: '纯文本' }] }),
  ] },
  { kind: 'feishu_app', label: '飞书应用（lark-cli 私聊 / 发群）', platform_label: '飞书', config_schema: [
    f('receive_type', '接收方类型', 'select', { required: true, default: 'open_id', options: [{ value: 'open_id', label: '用户（open_id）' }, { value: 'chat_id', label: '群（chat_id）' }] }),
    f('receive_id', '接收方 ID', 'text', { required: true, placeholder: 'ou_xxx 或 oc_xxx' }),
    f('identity', '发送身份', 'select', { default: 'bot', options: [{ value: 'bot', label: '机器人' }, { value: 'user', label: '用户' }] }),
  ] },
  { kind: 'feishu_doc', label: '飞书文档（实验性）', platform_label: '飞书', config_schema: [
    f('folder_token', '目标文件夹 token', 'text', { placeholder: 'fldcnxxxx', help: '为空时写入「我的空间」根目录' }),
  ] },
  { kind: 'wecom_webhook', label: '企业微信群机器人', platform_label: '微信', config_schema: [
    f('webhook_url', 'Webhook 地址', 'secret', { required: true, placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…' }),
    f('mention_all', '推送时 @所有人', 'bool', { default: false }),
  ] },
  { kind: 'serverchan', label: 'Server酱（服务号推送）', platform_label: '微信', config_schema: [
    f('sendkey', 'SendKey', 'secret', { required: true, help: '支持 Turbo 版（SCT 开头）和 Server酱³（sctp 开头）' }),
    f('channel', '消息通道', 'text', { placeholder: '9（方糖服务号）', help: '可选，多个用竖线分隔' }),
  ] },
  { kind: 'pushplus', label: 'PushPlus', platform_label: '微信', config_schema: [
    f('token', '用户 Token', 'secret', { required: true }),
    f('topic', '群组编码', 'text', { help: '一对多推送时填写' }),
  ] },
  { kind: 'wxpusher', label: 'WxPusher', platform_label: '微信', config_schema: [
    f('mode', '推送方式', 'select', { default: 'spt', options: [{ value: 'spt', label: 'SPT 极简推送' }, { value: 'app', label: 'appToken + UID' }] }),
    f('spt', 'SPT', 'secret'),
    f('app_token', 'appToken', 'secret'),
    f('uids', 'UID 列表', 'text', { placeholder: 'UID_xxx,UID_yyy' }),
  ] },
  { kind: 'qq_onebot', label: 'QQ（NapCat OneBot）', platform_label: 'QQ', config_schema: [
    f('target_type', '发送到', 'select', { required: true, default: 'private', options: [{ value: 'private', label: '私聊' }, { value: 'group', label: '群' }] }),
    f('target_id', 'QQ 号 / 群号', 'text', { required: true, placeholder: '10001' }),
    f('max_parts', '最多分段', 'number', { default: 6, help: '每段不超过 1500 字，段间隔 1.5 秒' }),
  ] },
  { kind: 'email_smtp', label: '邮箱（SMTP）', platform_label: '邮箱', config_schema: [
    f('host', 'SMTP 服务器', 'text', { required: true, default: 'smtp.qq.com' }),
    f('port', '端口', 'number', { default: 465 }),
    f('username', '账号', 'text', { required: true, placeholder: 'name@example.com' }),
    f('password', '授权码', 'secret', { required: true, help: 'QQ 邮箱需在「设置 → 账户」里生成授权码，不是登录密码' }),
    f('to', '收件人', 'text', { required: true, placeholder: '多个用逗号分隔' }),
    f('attach_md', '附带完整版 Markdown', 'bool', { default: true }),
  ] },
  { kind: 'local_archive', label: '本地归档', platform_label: '本地', config_schema: [
    f('formats', '保存格式', 'select', { default: 'md,html,json', options: [{ value: 'md,html,json', label: 'Markdown + HTML + JSON' }, { value: 'md', label: '仅 Markdown' }] }),
  ] },
]

export function initialChannels(now: number): ChannelDTO[] {
  const at = (minAgo: number) => new Date(now - minAgo * 60_000).toISOString()
  return [
    { id: 'ch-feishu-bot', kind: 'feishu_webhook', name: '飞书 · 情报群机器人', enabled: true,
      config: { webhook_url: '••••9c1e', sign_secret: '••••a7f2', card_style: 'card' }, last_result: { ok: true, detail: '已发送 2 段卡片', at: at(190) } },
    { id: 'ch-serverchan', kind: 'serverchan', name: '微信 · Server酱', enabled: true,
      config: { sendkey: '••••Q8rT', channel: '9' }, last_result: { ok: true, detail: 'pushid 1846203', at: at(190) } },
    { id: 'ch-qq', kind: 'qq_onebot', name: 'QQ · 私聊主号', enabled: true,
      config: { target_type: 'private', target_id: '10001', max_parts: 6 }, last_result: { ok: true, detail: '已发送 3 段', at: at(189) } },
    { id: 'ch-mail', kind: 'email_smtp', name: '邮箱 · 周报备份', enabled: false,
      config: { host: 'smtp.qq.com', port: 465, username: 'bureau@example.com', password: '••••kd3p', to: 'me@example.com', attach_md: true } },
    { id: 'ch-local', kind: 'local_archive', name: '本地归档', enabled: true,
      config: { formats: 'md,html,json' }, last_result: { ok: true, detail: '已写入 data/reports/', at: at(189) } },
  ]
}
