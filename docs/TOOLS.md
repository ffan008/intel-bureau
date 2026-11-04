# 第三方工具选型（调研时间 2026-10-28）

数据来自 GitHub API（星数、最近推送时间、是否归档）和项目 README。只选择满足以下条件的工具：只读、本地运行、维护活跃、能离线校验。

## 微信

| 工具 | 现状 | 结论 |
|---|---|---|
| [LifeArchiveProject/WeChatDataAnalysis](https://github.com/LifeArchiveProject/WeChatDataAnalysis) | 3,980★，2026-10-27 仍有推送，支持微信 4.x 与实时更新；本地 FastAPI `:10392`，提供 `/api/chat/accounts`、`/api/chat/sessions`、`/api/chat/messages`、`/api/chat/search` | **主选**。参考方案用的就是它，路由已核对。风险：本地 API 无鉴权且 CORS 为 `*`；会上报不含内容的使用事件（如 `app_open`、`message_page`）；桌面安装包为"高级版"构建，但我们只用开源的读取功能 |
| [hicccc77/WeFlow](https://github.com/hicccc77/WeFlow) | 15,581★，活跃；HTTP API `:5031`，有 Token 鉴权、`/api/v1/sessions`、`/api/v1/messages`，以及 SSE 主动推送 | **备选**。官方文档写明"不再内置任何读取/解密组件"，需要用户自行提供第三方 DLL，来源无法校验，所以不作为默认 |
| [sjzar/chatlog](https://github.com/sjzar/chatlog) | 9,179★，但仓库内容已清空（size=1），最后推送 2025-10-20 | **不用** |
| 小型 MCP 项目（wxq、wechatlog-mcp-server 等） | 星数个位到几十，维护者少 | 不用 |

## QQ

| 工具 | 现状 | 结论 |
|---|---|---|
| [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) | 11,877★，当天仍有推送；最新版 v4.18.41（2026-10-21）；OneBot 11 协议 | **主选**。Windows 用 `NapCat.Shell.zip`（使用本机已装的 QQ，SHA-256 `6801f93e…cf96b`），或 `NapCat.Shell.Windows.OneKey.zip`。WebUI 端口 6099；在 WebUI 中开启 HTTP 服务端（本项目约定 3010），可选 HTTP 客户端上报到 `http://127.0.0.1:8765/api/ingest/onebot` |
| [SXP-Simon/astrbot_plugin_qq_group_daily_analysis](https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis) | 529★，MIT | 只作为群日报提示词和报告结构的参考，不引入 |
| qq-nt-export、ntqq-db-decrypt | 1★ 和 0★，新项目 | 不用（不可信） |

风险提示：NapCat 属于非官方客户端框架，存在被风控的可能。**建议用一个"情报员小号"登录 NapCat**，拉进目标群，主号不受影响。推送到主号时，用小号私聊主号。

## 飞书

| 工具 | 现状 | 结论 |
|---|---|---|
| [larksuite/cli](https://github.com/larksuite/cli)（npm `@larksuite/cli`） | 官方，MIT，v1.0.98 | **主选**。`im +chat-list`、`im +chat-messages-list`、`im +messages-send`、`docs +create`。首次使用先 `lark-cli config init` 配置应用，再 `lark-cli auth login` 授权用户身份 |
| 飞书自定义机器人 Webhook | 官方 | 推送备选，无需应用权限 |

## 推送到微信

企业微信群机器人、Server酱（sct.ftqq.com）、PushPlus（pushplus.plus）、WxPusher（wxpusher.zjiecode.com）。都是官方 HTTP 接口，无需 Hook 微信。实现时以各自的官方文档为准。

## 大模型

本机 `claude` CLI 为 2.1.312，支持 `-p --output-format json --json-schema`。环境变量里没有任何模型 API Key，用户可以在「智能体」页面填写 OpenAI 兼容接口（DeepSeek、通义、Kimi、智谱、硅基流动、OpenRouter、Ollama）的密钥。
