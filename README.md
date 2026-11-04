# 情报局工作台（Intel Bureau）

> **第一次用？先看 [新手使用说明.md](新手使用说明.md)（或双击打开「新手使用说明.html」）。**
> **Windows**：双击「一键安装并启动.bat」。**macOS**：双击「一键安装并启动.command」（详见 [docs/SETUP_MAC.md](docs/SETUP_MAC.md)）。
> 想接微信 / QQ / 飞书，再双击「安装接入工具.bat」（三个工具已随包带好，许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）。
> **macOS 要安装包（双击即用、不用终端）**：`bash scripts/build-macos-app.sh` 生成 `.app` + `.dmg`，详见 [docs/BUILD_MAC_APP.md](docs/BUILD_MAC_APP.md)。

每天按你设定的时间，从你加入白名单的**微信群、QQ 群、飞书群**采集消息，提炼出有价值的情报，生成「每日风向标」，推送到飞书 / 微信 / QQ / 邮箱（可多选），并在本地的「AI Agent 作战大屏」里实时展示整个过程。

- **只读、只在本机运行**：服务只监听 `127.0.0.1:8765`，不上云；只有白名单群会被读取和存储。
- **每条情报都有出处**：附发言人、时间和原文摘录，摘录必须与原消息逐字一致，否则剔除；原文里找不到的数字标「待核实」。
- **计数由代码生成**：报告里的条数、序号、统计数字都由程序计算，大模型只写文字。
- **看风向而不只是流水账**：关键词与过去 7 天比较（z 值）找上升信号；话题记忆区分「新出现 / 持续发酵 / 重复」。
- **风险只标注、不降权**：合规、广告引流、金钱、账号等灰色内容照常提取和扩展，只加风险标签和免责声明，是否采用由你判断；涉及个人隐私的内容剔除；诈骗、伪造证件等违法高危内容只记录、不扩展成教程。
- **没有模型也能用**：默认用离线规则提取；同意后才会把群聊内容发给云端模型。

## 架构

```
 ┌──────────────── 数据源（全部只读） ─────────────────┐
 │ 微信 PC 4.x ─▶ WeChatDataAnalysis 本地 API :10392 ─┐ │
 │ QQ NT ─▶ NapCatQQ（OneBot 11 HTTP :3010 / 上报）───┤ │
 │ 飞书 ─▶ lark-cli（官方 CLI）──────────────────────┤ │
 │ 导出文件 / 粘贴文本 ─▶ data/inbox/<platform>/ ────┤ │
 └────────────────────────────────────────────────────┘
                     ▼ 采集器 bureau/collectors
          统一消息 RawMessage → SQLite（data/bureau.db）
                     ▼ 流水线 bureau/pipeline（12 个阶段）
 collect → clean → stats → segment → extract(LLM) → merge
   → score → verify → compose(LLM) → render → deliver → archive
                     ▼ 推送通道 bureau/channels
   飞书机器人 / 飞书应用 / 企业微信 / Server酱 / PushPlus / WxPusher / QQ / 邮箱 / 本地归档
 FastAPI 127.0.0.1:8765 ── REST + SSE ──▶ Vue 3 作战大屏（web/dist）
          ▲ APScheduler 定时任务（cron，Asia/Shanghai，错过会补跑）
```

| 目录 | 内容 |
|---|---|
| `bureau/core/` | 配置、路径、数据库（WAL + FTS5）、事件总线、日志、安全、分词 |
| `bureau/pipeline/` | 12 个阶段与运行器（锁、取消、dry_run、阶段事件） |
| `bureau/llm/` | 大模型提供方：`claude_code`、`openai_compat`、`anthropic`、`offline`、`auto` |
| `bureau/api/` | REST 接口、SSE、安全中间件、静态托管 |
| `bureau/collectors/`、`bureau/channels/`、`bureau/integrations/` | 平台采集器、推送通道、第三方工具封装 |
| `bureau/research/`、`bureau/media/` | 联网研究（搜索、读网页、链接增强）、图片文字识别与文档解析 |
| `bureau/demo/` | 演示数据生成器（9 个群 × 7 天，固定随机种子） |
| `config/` | 设置样例、提示词（`prompts/`）、分类体系（`taxonomy.yaml`）、自定义词典（`dicts/`） |
| `web/` | 前端作战大屏 |
| `data/` | 数据库、报告、日志、缓存（已 gitignore） |

设计细节见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，接口见 [docs/API.md](docs/API.md)。

## 快速开始

支持 Windows 10/11 和 macOS（Intel / Apple 芯片）。需要 Python **3.12 以上**（3.13 实测可用）；
只有重新构建前端才需要 Node.js 20.19 以上（`web/dist` 已随包带好）。

### macOS

```bash
# 1. 安装（创建 .venv、安装依赖、修正文件权限、初始化配置）
bash scripts/setup.sh

# 2. 体检
.venv/bin/python -X utf8 -m bureau doctor

# 3. 先用演示数据跑一遍（不需要任何外部服务和模型）
.venv/bin/python -X utf8 -m bureau demo seed
.venv/bin/python -X utf8 -m bureau run --demo --dry-run

# 4. 启动工作台（用 Chrome 应用模式打开 http://127.0.0.1:8765）
bash scripts/start.sh
```

双击版：`一键安装并启动.command`、`启动情报局.command`、`飞书重新授权.command`、`开机自启设置.command`。
macOS 上的平台可用性、与 Windows 的对应关系见 [docs/SETUP_MAC.md](docs/SETUP_MAC.md)。

### Windows

```powershell
# 1. 安装（创建 .venv、安装依赖、构建前端、生成配置）
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 2. 体检：每个平台、模型、通道的状态和修复建议
.venv\Scripts\python.exe -X utf8 -m bureau doctor

# 3. 先用演示数据跑一遍（不需要任何外部服务和模型）
.venv\Scripts\python.exe -X utf8 -m bureau demo seed
.venv\Scripts\python.exe -X utf8 -m bureau run --demo --dry-run

# 4. 启动工作台（用 Edge 应用模式打开 http://127.0.0.1:8765）
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

报告保存在 `data/reports/<日期>/<报告编号>.{md,html,json}`，HTML 版可以离线打开。

### 命令行

| 命令 | 说明 |
|---|---|
| `python -m bureau serve [--port 8765] [--open]` | 启动服务 |
| `python -m bureau run [--demo] [--dry-run] [--platforms wechat,qq] [--window-hours 24]` | 立即运行一次，控制台打印各阶段进度 |
| `python -m bureau doctor` | 体检表格 |
| `python -m bureau demo seed [--scale 1.0]` / `demo clear` | 写入 / 清除演示数据 |
| `python -m bureau groups refresh [--platform qq]` | 从平台拉群列表 |
| `python -m bureau init` | 初始化配置与数据库 |

### 开机自启

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1     # 登录后用 pythonw 在后台启动
powershell -ExecutionPolicy Bypass -File scripts\uninstall-autostart.ps1   # 取消
```

macOS：

```bash
bash scripts/autostart.sh on      # 注册 LaunchAgent，登录后后台启动（不弹窗口）
bash scripts/autostart.sh off     # 取消并停止后台服务
bash scripts/autostart.sh status  # 看状态
```

自启只为当前用户注册，不需要管理员权限。电脑关机错过的定时任务，下次启动时会补跑一次（默认只补 36 小时以内的）。

## 接入各平台

1. 在「情报源」页面选择平台和适配器，填写配置，点「测试连接」。
2. 点「刷新群列表」，把要关注的群加入白名单。**只有白名单群会被读取和存储。**
3. 在「调度中心」设置出报时间和推送通道。首次启动会自动创建「晨报」（每天 08:00，推送到本地归档）。

> **在 macOS 上**：飞书可以直连（lark-cli 用 Node 跑）；微信也可以直连——装 WeChatDataAnalysis 的
> **macOS 版**（`-mac-arm64.dmg`），它的 API Token 留空即可（程序自动读 WDA 自己的运行配置）。
> 只有 QQ 的采集工具仍是 Windows 程序，Mac 上建议导入聊天记录。详见 [docs/SETUP_MAC.md](docs/SETUP_MAC.md) 第三节。

| 平台 | 推荐方式 | 接入指南 |
|---|---|---|
| 微信 | WeChatDataAnalysis 本地 API | [docs/SETUP_WECHAT.md](docs/SETUP_WECHAT.md) |
| QQ | NapCatQQ（OneBot 11），建议用「情报员小号」 | [docs/SETUP_QQ.md](docs/SETUP_QQ.md) |
| 飞书 | 官方 lark-cli（用户身份） | [docs/SETUP_FEISHU.md](docs/SETUP_FEISHU.md) |
| 推送 | 飞书 / 企业微信 / Server酱 / PushPlus / WxPusher / QQ / 邮箱 | [docs/SETUP_PUSH.md](docs/SETUP_PUSH.md) |

暂时接不了平台时，可以把导出的聊天记录（WeChatDataAnalysis / WeFlow / ChatLab JSON、CSV，或复制粘贴的文本）拖进「情报源」页面的导入区，或放进 `data/inbox/<平台>/`。

### 大模型

默认 `auto`：优先已配置密钥的 API，其次本机 `claude` CLI，最后离线规则提取。

| 提供方 | 说明 |
|---|---|
| `openai_compat` | 预设 DeepSeek、通义千问（DashScope 兼容模式）、Kimi、智谱、硅基流动、OpenRouter、本地 Ollama |
| `anthropic` | Anthropic Messages API，地址可改 |
| `claude_code` | 本机 Claude Code CLI（`claude -p --output-format json`），不调用任何工具，在空的临时目录运行 |
| `offline` | 不需要模型：按线索词、链接、数字打分，只摘录原文 |

提示词在 `config/prompts/`，可以在「智能体」页面修改；v2 用到的文件见下一节。

**费用上限。** `llm.max_cost_cny` 默认每次运行 5 元（按 token 估算），到达后剩下的块改用离线规则，日志里会提示；设为 0 表示不限。本机 `claude` CLI 默认用的是最贵的模型（一次极小调用约 0.2 元），正式使用前建议在「智能体」页把 Claude Code 的模型改成更便宜的型号，或改用 DeepSeek 这类 OpenAI 兼容接口。

## v2：情报 + 知识库

规格见 `docs/V2_KNOWLEDGE.md`，接口见 `docs/API.md` 末尾的「v2」一节。

- **跨群话题。** 合并分两级：先合并同一条情报（v1 的规则），再把讲同一件事的要点合并成话题。一个话题是一条情报，前 `pipeline.max_features` 个（默认 12，8~15）写成专题文章，其余进「快讯」。
- **报告 12 个板块。** 当日 HTML 左侧是板块标签，用纯 CSS（`:target`）切换，不含脚本，飞书和邮件里也能打开；内容区最宽 760px；长内容折叠在 `<details>` 里。图片复制到 `data/reports/<日期>/<报告ID>_assets/`，HTML 用相对路径引用。
- **原文照录。** 提示词原文、网盘提取码由代码从数据库原文截取，不交给模型改写；对不上原文的直接丢弃。
- **风险策略。** `pipeline.risk_policy`：`label`（默认，只标注、附固定免责声明、不扣分，可以进头条和专题）、`flag`（v1：降权）、`drop`（剔除）。不论哪种策略，`违法高危` 只进风险板块，不成为专题，不做联网扩展，不写步骤；主要是某个人手机号、住址等的 `隐私` 内容整条剔除。新增的风险类别不写进 `config/taxonomy.yaml`，补充词表在 `config/taxonomy_v2.yaml`。
- **图片和文档。** 有取回信息的图片和文件不再丢弃，正文换成 `[图片#m12]`、`[文件:名称#m13]` 占位符供模型引用；被引用的由 `bureau.media` 取回、OCR、解析正文（`media.*` 设置）。
- **联网研究。** `bureau.research` 为每篇专题检索 `research.per_article_queries` 个词（不含群名、昵称、手机号），读取网页写「扩展研究」，并补全 GitHub / X 等链接的元数据。需要 `privacy.cloud_llm_consent=true` 和一个可用的模型；费用计入单次运行的费用上限。密钥在 `secrets.yaml` 的 `research.deepseek_api_key`（留空复用 `llm.openai_compat.api_key`）和 `research.github_token`。
- **推送与飞书文档。** 先投飞书文档这类文档通道，拿到链接后重新生成推送版（≤1800 字，全部专题标题 + 资源计数 + 直达链接），再投其它通道。
- **知识库。** 每篇专题按话题指纹写入知识库；同一话题再出现时合并更新（追加「{日期} 更新」、来源合并、保留历史版本）。仅预览（`--dry-run`）的运行也写知识库，同一天重跑只刷新当天内容。
- **提示词文件。** v2 读 `config/prompts/extract_v2.md`、`article.md`、`digest.md`、`research_queries.md`；`extract.md`、`compose.md`、`merge.md` 是 v1 的（`merge.md` 在开启 `llm.merge_judge` 时仍会用到）。
- **没有模型时**用离线模板：标题、要点、步骤、原话都摘自原文，不写扩展研究，其余板块照常。

**从 v1 升级。** 数据库迁移到版本 2，只新增 `reports.v2_data` 列和 `kb_articles`、`kb_versions`、`kb_fts` 表，迁移前自动备份到 `data/backups/`。已有的 `settings.yaml` 里写死的旧值不会被新默认值覆盖，需要手动改：`pipeline.risk_policy: label`、`pipeline.risk_penalty: 0`、`pipeline.max_features: 12`。

## 安全与隐私

- **云端模型需要你同意。** `privacy.cloud_llm_consent` 默认为 `false`，此时一律使用离线规则提取（本地 Ollama 不受限）。大屏和体检都会提示当前是否处于离线模式。
- **只监听本机。** 服务绑定 `127.0.0.1`；中间件只接受 Host 为 `127.0.0.1:8765` 或 `localhost:8765` 的请求（防 DNS 重绑定）；不开启 CORS。
- **访问令牌。** 除 `/api/session`、`/api/health`、`/api/ingest/onebot` 外，所有接口都要带 `X-Bureau-Token`。令牌在首次运行时随机生成，保存在 `config/secrets.yaml`。
- **密钥不外泄。** 密钥只存在 `config/secrets.yaml`（已 gitignore）；接口只返回 `••••末4位`；日志会自动替换已知密钥和 URL 里的 token。
- **脱敏。** 清洗阶段默认把手机号、邮箱、身份证号、银行卡号、微信号替换成占位符，报告、推送和发给模型的内容里不会出现这些信息。本地数据库里的原始消息保留原文（用于回看上下文），按保留期清理。
- **保留期。** 原始消息默认保留 30 天（`privacy.retention_days`），演示数据不受影响。
- **提示词注入防护。** 聊天内容放在 `<chat_log>` 标签里，系统提示声明其中的指令只是数据；模型输出必须通过 JSON 校验。
- **WeChatDataAnalysis 的本地 API 没有鉴权，而且开放了 CORS（`*`）。** 运行期间不要打开不可信网页，不用时关掉它。
- **不做个人微信 Hook。** 微信侧只读；推送走企业微信机器人或公众号类推送服务。QQ 侧建议用小号登录 NapCat。

## 常见问题

**访问 `http://127.0.0.1:8765` 只看到"服务已启动"提示页？**
前端还没构建。运行 `scripts\setup.ps1`（Windows）或 `bash scripts/setup.sh`（macOS），或在 `web` 目录执行 `npm ci` 和 `npm run build`。

**macOS 上双击 `.command` 没反应 / 只弹出空终端？**
执行权限丢了（从 Windows 拷过来常见）：`bash scripts/setup.sh` 会补上，或 `chmod +x *.command scripts/*.sh`。
中文 OCR 缺语言包、launchd 自启报 I/O error 等问题见 [docs/SETUP_MAC.md](docs/SETUP_MAC.md) 第五节。

**报告里都是"程序从原文摘录"的文字，不够流畅？**
现在在用离线规则提取。在「智能体」页面配置一个模型并打开「允许使用云端模型」，或者在本机运行 Ollama。

**为什么某个群没有被采集？**
确认它在白名单里、对应平台已启用、`doctor` 里该平台是「正常」。微信需要 WeChatDataAnalysis 正在运行，QQ 需要 NapCat 已登录并开启 HTTP 服务。

**电脑关机错过了 08:00 的晨报？**
下次启动服务时会自动补跑一次。补跑的窗口从上次成功运行开始（最多回溯 72 小时）。

**cron 里的星期怎么写？**
按标准 cron：`0` 或 `7` 是周日，`1` 是周一，`1-5` 是工作日；也可以写 `mon-fri`。「日」和「周」不能同时限定（例如 `0 9 1 * mon`），保存时会被拒绝。

**大屏上点「立即出报」，演示运行为什么要十几秒？**
离线规则几秒内就能跑完 12 个阶段，动画会一闪而过，所以大屏触发的演示运行每个阶段至少展示 1.1 秒（`app.demo_stage_min_ms`，设为 0 关闭）。数据和结果不受影响；真实运行和命令行运行不会放慢。

**提示"另一个进程正在运行流水线"？**
同一时间只允许一次运行。命令行的 `run` 和服务进程共用一把锁，等它结束即可。

**控制台中文乱码？**
运行 Python 时加 `-X utf8`；脚本和命令行入口已经把输出设为 UTF-8。

**怎么清掉演示数据？**
`python -m bureau demo clear`，或在「系统」页面点「清除演示数据」。它会删除所有演示群、消息、运行记录和报告文件，不影响真实数据。

## 开发

```powershell
# Windows
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -X utf8 -m pytest -q
```

```bash
# macOS
bash scripts/setup.sh --dev
.venv/bin/python -X utf8 -m pytest -q
```

测试使用临时目录，不会改动 `data/` 和 `config/settings.yaml`。外部服务都用假服务器（httpx MockTransport）测试。
macOS 上如果 pytest 报 `FileExistsError`（某些受限终端会拦 mkdir），加 `--basetemp=/tmp/pt` 即可。
