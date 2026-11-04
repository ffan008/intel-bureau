# 情报局 v2：情报 + 知识库 · 改造规格

> 本文是 v2 改造的唯一依据，与 `docs/ARCHITECTURE.md`、`docs/API.md` 冲突时以本文为准。实现代理必须先读完本文。

## 0. 用户诉求（原话要点）

1. 现在的风向标和参考看板差距大。要的是**把有用信息串起来、能当知识库**；情报局不只是获取情报，也是**获取和学习知识**的地方。
2. 群里的信息要用 **AI 联网搜索扩展**成更完整的专题知识文章，**每天多篇**；或者在一个 HTML 里分板块，**点击切换**查看。
3. **不要**学参考看板的排版：它文字太长、可读性差、没有按板块切换。
4. 风险内容（合规、广告引流、金钱、账号运营等）**不降权、不剔除**：用户就是要学赚钱方法、项目经验、账号运营。可以**标注风险和免责提示**，是否使用由用户自己判断。**只有涉及个人手机号等隐私的**可以降低或剔除。
5. 群里**有用的图片和文档**也要提取出来，写进风向标或知识内容；文档要读取内容后提炼，不能只给附件。只有确认无用的才剔除。
6. 参考一份公开的飞书风向标知识库是怎么设计的。

## 1. 对照参考

**参考 A：`某单群日报看板（HTML）`**（单群日报，1,250 条消息）

结构：一句话总结 → 今日三件事 → 全部链接总表（34 条，地址和提取码原样照录）→ 模型选型与实测 → 提示词原文照录（不压缩）→ 方法与 SOP → 风险与踩坑 → 收益与数据（标明"群友自述"）→ 金句。

问题：一页到底、没有导航、段落过长。

**参考 B：某社群飞书知识库「2026-10-29 今日风向标」**（多群汇总）

- 当天总览页，带 13 篇专题子文档的直达链接。
- 外部资源表：
  - GitHub 高星项目（星数、语言、分享人、核心机制）
  - X/推特动态（点赞、转发数）
  - 公众号文章（字数、摘要）
  - 网盘资料（平台、提取码、分享人、直达链接）
- 社群快讯 / 遗珠、目录索引。
- 推送消息：今日 N 篇标题列表 + 各类资源计数 + 两个直达链接。

**我们 v1 的问题**（2026-10-30 03:49 真实测试：2,179 条 → 113 条情报）：
- 条目零碎（"字幕字号偏小的提示词调整法"），没有跨群串联成专题。
- 没有联网扩展，没有资源库和元数据。
- 提示词、提取码没有原样保留。
- 图片、文档被清洗阶段丢掉。
- 风险内容被降权（每个标签扣 0.6 分，并排除在头条之外）。

## 2. 风险策略（v2）

| 类别 | 处理 |
|---|---|
| 合规风险、平台规则、账号风险、金钱风险、广告引流、版权风险、未核实 | **照常提取、照常扩展、可以进头条和专题**，不扣分。文末加风险提示和固定免责声明 |
| 隐私（内容主要是某个普通人的手机号、住址、身份证号等） | 剔除该条，或只保留脱敏后的要点；PII 脱敏照旧 |
| 违法高危（诈骗、伪造证件或资质、盗号与买卖账号、洗钱、赌博、色情传播、涉及未成年人） | **照常记录和总结**（用户有权知道群里在讨论什么），放进「风险」板块并标注 `违法高危`；**不做联网扩展，不写成分步教程** |

- `pipeline.risk_policy` 新增 `label`（**新默认**）：只标注不扣分。`flag` 保留旧行为，`drop` 保留。
- `risk_penalty` 默认改为 0。
- 免责声明（固定文案，所有带风险标签的文章和条目末尾都要有）：
  > ⚠️ 风险提示：以上内容整理自群聊讨论与公开资料，仅供学习研究。涉及平台规则、账号与资金的操作可能违反服务条款或带来损失，是否采用请自行判断并承担责任。

## 3. 输出

### 3.1 当日 HTML（自包含，板块标签页切换）

- **布局**：左侧竖向标签列表，每项显示板块名和条目数；右侧是内容区，最大宽度 760px，行高 1.8，正文 16px。
- **段落**：每段不超过 4 行；长内容用 `<details>` 折叠，比如群内原话、长提示词、长表格。
- **切换**：必须**纯 CSS** 实现（radio 加 `:checked ~`，或 `:target`），不用 JavaScript。工作台的 CSP 禁止内联脚本，飞书和邮件里也跑不了 JS。
- **深色主题，可打印**。

板块（key 固定，顺序固定）：

| key | 标题 | 内容 |
|---|---|---|
| `overview` | 今日总览 | 一句话总结、今日风向 3~5 条、数据卡（消息、群、情报、文章、资源数）、今日 N 篇专题列表（可点击跳到 `articles` 对应篇）|
| `articles` | 专题文章 | 8~15 篇，模板见 §3.2；先显示列表卡片，点开看全文（用 details 或锚点）|
| `resources` | 资源库 | 按 GitHub / X / 公众号 / 网盘 / 视频 / 文档 / 其它分组的表格；网盘带提取码；GitHub 带星数、语言、简介；都写明分享人、群、时间 |
| `prompts` | 提示词原文 | 群里出现的完整提示词，**一字不改**，放代码块；附发言人、时间、用途 |
| `sops` | 方法与 SOP | 被验证过的做法，编号步骤 |
| `tools` | 工具与模型 | 选型对比、实测结论（谁、在什么场景、结论）|
| `data` | 收益与数据 | 群友自述的数字（标「群友自述，非平台口径」）|
| `risks` | 风险与踩坑 | 踩坑经验，加所有带风险标签的条目（含违法高危，只记录）|
| `quotes` | 金句与判断 | 原文引用 |
| `media` | 图片与文档 | 有用的图片（缩略图、OCR 要点、出处），以及文档正文提炼（文件名、类型、要点、出处）|
| `groups` | 分群摘要 | 活跃群各一张卡：一句话总结、三件事、各项计数 |
| `briefs` | 快讯与其余 | 没有进专题的其余情报，每条一行 |

### 3.2 专题文章模板（`body_md`）

```
# {序号}-{标题}
> 分类：{分类}｜来源：{群名}·{发言人}·{时间}（可多个）｜{风险标签}
**一句话**：{hook}
## 背景与群内讨论
（2~4 段，引用群内原话用 > 引用块，标发言人和时间）
## 关键做法
1. … （编号步骤；原文没有步骤时写「要点」）
## 提示词 / 参数原文
（代码块，原文照录）
## 扩展研究
（联网搜索得到的补充；每条结论后标来源 [1][2]；和群内说法冲突时写明）
## 资源
（链接、提取码、GitHub 星数等）
## 适用范围、成本与数据
（群友自述的数字要标明）
## 风险提示
（风险标签与说明；末尾附固定免责声明）
---
参考：[1] 标题 · 链接 …
```

数字、序号、计数由代码生成。提示词原文、提取码、链接**必须由代码从数据库原文复制**，不交给模型改写。

### 3.3 知识库（跨天持久）

- 每篇专题文章写入知识库条目，按话题指纹匹配。
- 相同话题再出现时**合并更新**：
  - 追加一节「{日期} 更新」
  - 来源合并
  - 保留历史版本
- 新话题新建条目。
- 工作台新增「知识库」页面：搜索、分类筛选、标签筛选、阅读、历史版本。

### 3.4 飞书知识库树（`feishu_doc` 通道升级）

```
情报局知识库（空间；没有就自动创建，记住 space_id）
└─ 每日风向标
   └─ 2026-10-30（今日风向标）       ← 当天总览页：总览 + 专题直达 + 资源表 + 快讯 + 目录
      ├─ 01-{专题标题}
      ├─ 02-{专题标题}
      └─ …
```

- 通道配置新增 `mode`：`single`（v1：一篇文档）或 `wiki`（**新默认**）。另有 `space_id`、`parent_node`（可空，自动创建）。
- 图片尽力上传进文档，失败就跳过并在文档里写「图片见工作台」。
- 返回当天总览页链接（`DeliveryResult.url`）。

### 3.5 推送消息（`summary_md`，不超过 1800 字）

```
今日{群范围}风向标（{日期}）已更新！
📌 今日 {N} 篇深度实操拆解：
1. … （全部标题）
🔥 外部精选资源：🐙 GitHub {n} 项 · 🐦 X {n} 条 · 📑 公众号 {n} 篇 · 💾 网盘 {n} 套
⚠️ {n} 条带风险提示（详见风险板块）
👉 今日风向标直达：{doc_links.feishu_doc 或 dashboard_url}
👉 知识库目录：{知识库根链接，如有}
```

投递顺序：先投 `feishu_doc` 这类文档通道，拿到 url 填进 `ReportPayload.doc_links`，再重新生成 `summary_md` / `summary_text`，然后并发投其它通道。

## 4. 流水线变化（仍是 12 个阶段，大屏不变）

- **clean**：图片和文件消息**不再丢弃**，作为媒体候选保留，正文用占位符 `[图片#mXX]`、`[文件:名称#mXX]` 进入对话块，让模型能引用。表情包照旧丢弃。
- **extract**：schema 扩展：
  - `prompts[]`（msg 引用）
  - `sop_steps[]`
  - `data_points[]`（value, unit, msg, self_reported）
  - `quotes[]`（msg）
  - `tool_notes[]`（tool, verdict, msg）
  - `media_refs[]`（msg, why）
  - `privacy`（bool）
  - `links[]` 带 `kind`

  提示词改写：删掉"不得写成教程推荐"，改成"灰色内容照常完整提取方法和链接，只需在 risk_flags 标注"。违法高危照常提取要点但标 `违法高危`。
- **verify**：`prompts`、`quotes`、`data_points` 的引用必须指向块内真实消息。提示词原文、提取码由代码从消息原文截取。
- **score**：按 §2 执行。专题按跨群合并后的话题选出前 `pipeline.max_features`（默认 12，范围 8~15）篇；`违法高危` 不能成为专题文章，只进 `risks`。
- **compose**（内部子步骤，阶段名不变）：
  1. 媒体：下载被引用的图片和文件，图片 OCR，文档解析出正文。
  2. 研究：每篇专题由模型生成 2~3 个检索词，调用 `research.web_search`，取前几条，用 `research.fetch_page` 读正文。
  3. 链接增强：所有链接调用 `research.enrich_link`。
  4. 写专题：调用模型（`config/prompts/article.md`），输出结构化 JSON，代码套 §3.2 模板。
  5. 写分群摘要（`config/prompts/digest.md`）。

  没有模型时用离线模板：不写扩展研究，其余照常。
- **render**：生成 `full_md`（按板块分节）、`sections`、`articles`、`resources`，以及 §3.1 的 HTML。图片复制到 `data/reports/<date>/<report_id>_assets/`。
- **deliver**：按 §3.5 的顺序投递。
- **archive**：写入知识库，按 §3.3 合并。

## 5. 接口契约（B 实现、A 调用，签名固定）

`bureau/research/__init__.py`：

```python
@dataclass
class ResearchContext:
    settings: dict; secrets: dict; data_dir: Path
    max_searches: int; max_fetches: int
    used_searches: int = 0; used_fetches: int = 0; cost_usd: float = 0.0
    logger: logging.Logger

class SearchHit(BaseModel): title: str; url: str; summary: str = ""; content: str | None = None; site: str | None = None; published_at: str | None = None
class PageContent(BaseModel): url: str; title: str | None; markdown: str; ok: bool; error: str | None = None
class LinkMeta(BaseModel):
    url: str; kind: Literal["github","x","wechat_article","netdisk","video","doc","web","other"]
    title: str | None = None; description: str | None = None
    meta: dict[str, Any] = {}      # github: stars/language/forks/updated_at；x: author/likes/retweets/text；wechat: author/words；netdisk: provider
    code: str | None = None; ok: bool = True; error: str | None = None

async def web_search(ctx: ResearchContext, query: str, *, count: int = 5) -> list[SearchHit]
async def fetch_page(ctx: ResearchContext, url: str, *, max_chars: int = 12000) -> PageContent
async def enrich_link(ctx: ResearchContext, url: str, *, context_text: str = "") -> LinkMeta   # context_text 用于识别提取码
def classify_link(url: str) -> str                                                         # 同步，纯规则
```

`bureau/media/__init__.py`：

```python
class MediaResult(BaseModel):
    ok: bool; kind: Literal["image","file","video"]; path: str | None = None; filename: str | None = None
    mime: str | None = None; size: int | None = None; width: int | None = None; height: int | None = None
    sha256: str | None = None; error: str | None = None

async def fetch_media(app_cfg: dict, secrets: dict, platform: str, attachment: dict, dest_dir: Path) -> MediaResult
async def ocr_image(path: Path, *, mode: str = "windows", settings: dict | None = None, secrets: dict | None = None) -> str
async def extract_document(path: Path, *, max_chars: int = 20000) -> str     # pdf/docx/xlsx/pptx/txt/md/csv/html
```

- 采集器在 `attachments[].extra.fetch` 里写平台取回所需的描述（B 定义，A 原样传回）。
- 所有函数都不抛异常（参数错误除外），失败时返回 `ok=False` 或空串，并带上中文 error。

## 6. 设置（`config/settings.example.yaml` 新增）

```yaml
pipeline:
  risk_policy: label        # label / flag / drop
  risk_penalty: 0
  max_features: 12
  group_digest_min_msgs: 30
  group_digest_max: 12
research:
  enabled: true
  provider: deepseek        # deepseek / none
  max_searches: 30          # 每次运行
  max_fetches: 30
  per_article_queries: 2
  github_enrich: true
  x_enrich: true
media:
  enabled: true
  ocr: windows              # windows（本机离线）/ llm（视觉模型，需云端同意）/ off
  max_images: 40
  max_files: 15
  max_file_mb: 20
```

- 密钥：`secrets.yaml` 里的 `research.deepseek_api_key`（留空就复用 `llm.openai_compat.api_key`），以及 `research.github_token`（可选）。
- `PUT /api/settings` 的 SECTIONS 加上 `research`、`media`，并且这两个密钥也要走 secrets，不写进 settings.yaml。
- 云端同意：联网搜索、`ocr: llm` 都要求 `privacy.cloud_llm_consent=true`，否则跳过并在日志说明。
- 检索词里**不得**出现群名、发言人昵称、手机号；只能用话题、工具名、项目名。

## 7. API 变化（前后端契约）

- `GET /api/reports/{id}` 增加：
  - `sections: Record<key, string>`
  - `articles: ArticleDTO[]`
  - `resources: ResourceDTO[]`
  - `media: MediaDTO[]`
  - `groups: GroupDigestDTO[]`
  - `section_counts: Record<key, number>`
- `GET /api/reports/{id}/assets/{name}?token=`：报告图片。只允许读这份报告的 assets 目录，防止路径穿越。
- `GET /api/kb?q=&category=&tag=&limit=&offset=` → `{items: KbSummaryDTO[], total, categories: {name,count}[], tags: {name,count}[]}`
- `GET /api/kb/{id}` → `KbArticleDTO`（含 `body_md`、`versions[]`、`sources[]`、`related[]`）
- `GET /api/overview` 增加 `kb: {total, updated_today, new_today}`

```ts
interface ArticleDTO { id: string; seq: number; title: string; hook: string; category: string; body_md: string;
  risk_flags: string[]; risk_note?: string; sources: {group_name: string; platform: Platform; sender: string; sent_at: string}[];
  images: string[]; kb_id?: string; research_refs: {n: number; title: string; url: string}[] }
interface ResourceDTO { kind: 'github'|'x'|'wechat_article'|'netdisk'|'video'|'doc'|'web'|'other'; title: string; url: string;
  code?: string; meta: Record<string, unknown>; note?: string; shared_by?: string; group_name?: string; sent_at?: string }
interface MediaDTO { kind: 'image'|'file'; name: string; url?: string; ocr_text?: string; summary?: string; why?: string;
  group_name?: string; sender?: string; sent_at?: string; article_seq?: number }
interface GroupDigestDTO { group_key: string; group_name: string; platform: Platform; messages: number; summary: string;
  highlights: string[]; counts: {links: number; prompts: number; sops: number; data: number} }
interface KbSummaryDTO { id: string; title: string; category: string; tags: string[]; hook: string; risk_flags: string[];
  updated_at: string; created_at: string; versions: number; sources: number }
interface KbArticleDTO extends KbSummaryDTO { body_md: string; versions: {at: string; report_id: string; note: string}[];
  sources: {group_name: string; sender: string; sent_at: string}[]; related: {id: string; title: string}[] }
```

## 8. 所有权

| 代理 | 路径 |
|---|---|
| **A2 后端** | `bureau/pipeline/`、`bureau/core/`（含 schema 迁移和新的 `store/kb.py`）、`bureau/api/`、`bureau/llm/`、`config/`、`tests/`（不含 `tests/integrations/`）、`README.md`、`docs/API.md` 增补 |
| **B2 集成** | 新建 `bureau/research/`、`bureau/media/`；`bureau/collectors/*`（只补 `attachments[].extra.fetch`）；`bureau/channels/feishu_doc.py`、`feishu_app.py`；`bureau/integrations/`；`scripts/tools/`；`docs/SETUP_FEISHU.md`；`tests/integrations/` |
| **C2 前端** | `web/` |
| **Lead** | `bureau/contracts.py`、`bureau/collectors/__init__.py`、`bureau/channels/__init__.py`、本文、`requirements.txt` |

`bureau/contracts.py` 已经新增 `ArticleBrief`、`ResourceBrief`、`ReportPayload.articles / resources / sections / assets_dir / doc_links`、`DeliveryResult.url`，直接用。

## 9. 运行窗口约束（重要）

- 工作台服务**正在运行**，内存里是 v1 代码。每天 08:00 会用**真实数据**跑「晨报」。
- **禁止**：重启或停止服务；在 07:45~08:45 之间对真实 `data/` 运行流水线或命令行；修改运行时会读取的文件，包括 `config/prompts/*.md`、`config/taxonomy.yaml`、`config/settings.yaml`、`config/secrets.yaml`。新提示词写成**新文件**（`article.md`、`digest.md`、`extract_v2.md`），由 v2 代码读取；旧文件留给 08:00 的旧代码用，**不要改动**。
- `web/dist` 正在被服务托管，**不要覆盖**。C2 验证构建时用 `vite build --outDir dist-v2`，验证完删掉。
- 所有验收运行都用沙箱：
  - `$env:BUREAU_DATA_DIR='<项目目录>\data\sandbox-v2'`、`$env:BUREAU_CONFIG_DIR='<项目目录>\data\sandbox-v2-config'`
  - 配置从 `config/` 复制，**不复制 secrets.yaml**，自动生成新的。
  - 不接真实账号，不发真实消息，不调用付费接口，B2 的少量连通性测试除外，见其任务说明。
- 不要执行 git 命令；不要全局安装；Python 依赖已由 Lead 装好（pypdf、python-docx、openpyxl、python-pptx、pillow）。

## 10. 验收

1. `pytest -q` 全部通过，含新增测试。
2. 沙箱演示数据跑通 12 个阶段，生成的 HTML：
   - 12 个板块都能用纯 CSS 切换
   - 至少 8 篇专题，每篇都有完整模板
   - 资源库至少 3 类
   - 提示词原文和数据库原文逐字一致
   - 风险条目没有被降权，带免责声明
   - 违法高危条目只出现在 `risks` 板块
3. 知识库：同一份演示数据连跑两次，第二次是合并更新而不是新建，可以看到版本历史。
4. 前端：报告阅读器有板块标签页；知识库页面能用；1920×1080 下没有溢出；mock 和真实接口字段一致。

## 11. 实施记录（2026-10-30，Lead）

上线后在真实数据上发现并修正的问题，以及和本规格的差异：

- **附件取回信息补写**：v1 采集器入库的消息没有 `attachments[].extra.fetch`，而入库是「重复就跳过」，所以旧消息的图片和文件永远取不回。现在：
  - `insert_messages` 遇到重复消息、且新拉到的版本带 fetch 而库里没有时，只补写附件，其它字段不变。
  - 手动运行（`trigger=manual`）按指定窗口完整重拉，不走游标。
  - 定时任务仍走游标增量。
- **DeepSeek 思考模式**：`deepseek-flash` 默认开启思考模式，推理内容计入 `max_tokens`，4096 的上限会把 JSON 截断。上线首跑 58 个块里有 27 个退回离线规则，总览和检索词的 JSON 也解析失败；思考模式下 temperature 也不生效。现在：
  - `openai_compat` 对 DeepSeek 接口默认发送 `thinking: {type: disabled}`，可在「智能体」页改为开启；服务商拒绝该参数时去掉后重试。
  - `llm.max_tokens` 默认改为 8192。
- **提示词板块**：群公告、风向标推送曾被识别成「提示词」。`extract_v2.md` 已明确：提示词只算写给 AI 模型或生成工具的指令。
- **飞书知识库树**：
  - 用户身份没有 `wiki:wiki` / `wiki:space:create` 权限，自动建「情报局知识库」空间会失败。通道已改为个人文档库（`space_id` 填数字 ID，`base_url` 填租户域名）。
  - 首次真实投递在建根节点时返回 131001；改用 `docs +create` 后，飞书返回 **10061：租户文档额度已用完**。需要租户管理员扩容，或删除不用的文档，之后重新投递即可，代码按 report_id 幂等。
- **链接增强需要云端同意**（A2 的选择）：链接增强会把链接发给外部服务（GitHub API 等），所以和联网搜索一样受 `privacy.cloud_llm_consent` 控制。
- **仅预览运行也写知识库**（A2 的选择）：同一天重跑只刷新当天的内容；话题记忆仍然只在正式运行时更新。