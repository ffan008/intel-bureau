# macOS 使用说明

> 这份文档讲**苹果电脑上怎么把情报局跑起来**，以及哪些能力和 Windows 版不一样。
> 只想赶紧用起来：双击根目录的 **「一键安装并启动.command」**，其余不用看。

---

## 一、三步启动

| 步骤 | 做什么 | 结果 |
|---|---|---|
| 1 | 双击 **「一键安装并启动.command」** | 自动建虚拟环境、装依赖、初始化数据库；第一次还会写入演示数据 |
| 2 | 等它自己打开浏览器窗口 | 看到深色作战大屏，顶部有 KPI、左侧有导航 |
| 3 | 按需在「情报源」页接入平台 | 见下面第三节 |

- 想让它**不用一直开着这个终端窗口**：双击 **「开机自启设置.command」** → 选 1。
- 以后每次启动：双击 **「启动情报局.command」**。
- 停止：关掉那个终端窗口，或按 `Ctrl+C`。

第一次打开时，如果 macOS 提示"无法打开，因为无法验证开发者"：在文件上**右键 → 打开**，或在
「系统设置 → 隐私与安全性」里点「仍要打开」。这是因为文件是从别的电脑拷过来的，不是真的有问题。

### 命令行等价写法

```bash
bash scripts/setup.sh          # 安装 / 更新依赖（--skip-web 跳过前端，--dev 带测试依赖）
bash scripts/start.sh          # 启动（--port 8766 换端口，--no-browser 不开窗口）
bash scripts/autostart.sh on   # 登录自启（后台常驻）；off 取消；status 看状态
bash scripts/feishu-reauth.sh  # 飞书重新授权（--status 只看状态）
```

---

## 二、环境要求

| 需要 | 说明 |
|---|---|
| macOS 12 以上（Intel 或 Apple 芯片都行） | 本项目所有改动在 Apple 芯片 + macOS 26 上实测通过 |
| Python 3.12 或更高 | 实测 3.13.12 正常。没有就 `brew install python@3.13` |
| 联网 | 第一次装 Python 依赖约 100 MB |
| （可选）Node.js 20.19+ | **只有重新构建前端时才需要**；`web/dist` 已带好，日常不用装 |
| （可选）tesseract | 中文图片的本地 OCR；`brew install tesseract tesseract-lang` |

不需要 Xcode、不需要 `py` 启动器、也不需要管理员权限。

---

## 三、各数据源在 Mac 上的实际情况

工作台本身是"读你电脑上的群聊 → 出报告"，所以**能不能接某个平台，取决于那个平台的工具支不支持 Mac**。
下面是实测/核对后的结论，别照 Windows 的教程硬套：

| 平台 | Mac 上能不能用 | 怎么做 |
|---|---|---|
| **飞书** | ✅ 能用 | 随包的 lark-cli 1.0.98 在 Mac 上正常（用 Node 跑）。「情报源 → 飞书 → 测试连接」→ 双击「飞书重新授权.command」 |
| **推送通道** | ✅ 全能用 | 飞书机器人 / 企业微信 / Server酱 / PushPlus / WxPusher / QQ / 邮箱 / 本地归档，都与系统无关 |
| **大模型** | ✅ 能用 | 离线规则（默认）／OpenAI 兼容（DeepSeek、通义、Kimi、Ollama…）／本机 `claude` CLI（若已装） |
| **微信** | ✅ 能直连（装 Mac 版 WDA 即可） | 装 **WeChatDataAnalysis 的 macOS 版**（`-mac-arm64.dmg`，原生 Apple Silicon 程序，不是 Windows 版），打开它、在它里面解密账号，然后在「情报源 → 微信 → 测试连接」。2.x 起它的本地接口要 API Token，**留空即可**——程序会自动读 WDA 自己的运行配置；也可以在「设置 → 接口与 MCP」里复制后手填 |
| **QQ** | ⚠️ 建议导入 | NapCat 官方以 Windows / Linux 为主，Mac 没有验证过的现成包。最稳的是同样用「导入聊天记录」 |

导入方式：**「情报源」页面的导入区**，或把文件放进 `data/inbox/wechat/`、`data/inbox/qq/`、`data/inbox/feishu/`。
支持的格式：WeChatDataAnalysis / WeFlow / ChatLab 的 JSON、CSV，以及直接复制的纯文本。

> 换句话说：**在 Mac 上，飞书和微信都能"全自动"；QQ 是"半自动"（导出后导入）。**
> 报告生成、知识库、定时任务、推送这些核心能力完全不受影响。

### 微信直连的两个前提（缺一个就连不上）

1. **WDA 要开着**，并且账号已经解密（WDA 里能看到会话列表）。它关掉，工作台就报“连不上 WeChatDataAnalysis”。
2. **微信版本要能被 WDA 读到**。WDA 是读本机微信的本地数据库；微信升到 WDA 还不认识的版本时，先在 WDA 里更新/重新获取密钥。

> WDA 的本地接口**没有跨进程加密、CORS 是 `*`**，任何本机程序都能读。不用的时候把它退出。
>
> 顺带一句：WeChatDataAnalysis 只读本机微信的库，不会动微信本身，也不会掉线。


---

## 四、和 Windows 版的对应关系

功能一样，只是外壳换成了 macOS 的东西：

| Windows | macOS | 说明 |
|---|---|---|
| `一键安装并启动.bat` | `一键安装并启动.command` | 双击即用，逻辑一致 |
| `启动情报局.bat` | `启动情报局.command` | 起服务 + 开大屏 |
| `飞书重新授权.bat` | `飞书重新授权.command` | 同一个授权流程 |
| — | `开机自启设置.command` | 交互菜单：设置 / 取消 / 查看状态 |
| `scripts\setup.ps1` | `scripts/setup.sh` | 建 `.venv`、装依赖、构建前端、修正权限、初始化 |
| `scripts\start.ps1` | `scripts/start.sh` | 起服务、等健康检查、开窗口 |
| Edge 应用模式 `--app=` | Chrome 应用模式 `--app=` | 没装 Chrome 就退回默认浏览器 |
| Windows 任务计划程序 | launchd（`~/Library/LaunchAgents`） | 登录后在后台跑，不弹窗口 |
| `pythonw.exe` 隐藏窗口 | launchd 无窗口运行 | 不需要额外处理 |
| Windows 系统 OCR（PowerShell） | macOS Vision，缺中文时用 tesseract | 设置项 `media.ocr` 名字仍叫 `windows`，按系统自动选引擎 |
| `.venv\Scripts\python.exe` | `.venv/bin/python` | |

代码里原来写死 Windows 的地方（OCR 脚本、lark-cli 的 `.exe`/`.cmd` 查找、Windows 盘符判断、提示文案）
都已经改成按平台判断，Windows 上的行为不变。

---

## 五、常见问题

**装依赖卡住 / 报网络错误？**
换网络或先开代理，再执行 `bash scripts/setup.sh`。pip 的报错会原样打出来。

**提示没有 Python 3.12？**
`brew install python@3.13`，然后重新双击「一键安装并启动.command」。
（3.12 / 3.13 / 3.14 都可以，脚本会自动找。）

**端口 8765 被占用？**
`bash scripts/start.sh --port 8766`。或者先看看是不是已经开着一个工作台（`bash scripts/autostart.sh status`）。

**双击 `.command` 只弹出一个空白终端窗口？**
文件的可执行权限丢了（从 Windows 拷过来常见）。执行一次 `bash scripts/setup.sh` 会自动补上；
也可以在「终端」里 `chmod +x *.command scripts/*.sh`。

**「开机自启设置」提示 launchd 拒绝了加载（Input/output error）？**
在**你自己桌面上的「终端」App**里执行：

```bash
bash "/Users/你的用户名/…/IntelBureau-v2/scripts/autostart.sh" on
```

从某些受限终端（比如应用内置的终端）调 launchctl 会被系统拒绝，这跟配置本身无关。

**图片里的中文识别不出来？**
本机 OCR 有两个引擎：macOS 自带的 Vision（默认只有拉丁语系）和 tesseract。
两个办法任选：① `brew install tesseract tesseract-lang`；② 「系统设置 → 通用 → 语言与地区」添加简体中文后重启工作台；
③ 也可以把「智能体 → 图片与文档 → OCR」改成「视觉模型」（需要打开云端同意）。

**想要和 Windows 上同一份数据？**
整个文件夹拷过来，**删掉 `.venv` 和 `web/node_modules`**（这两个是分平台的），再双击安装脚本。
`data/`（数据库、报告、知识库）和 `config/`（设置、密钥、提示词）原样保留就行。

---

## 六、实测记录（2026-11-04，Apple 芯片 + macOS 26 + Python 3.13.12）

- `bureau init` / `doctor` / `demo seed` / `run --demo --dry-run`：全部正常，12 个阶段跑完，报告落盘
- 服务 `127.0.0.1:8765`：健康检查、令牌鉴权、REST 接口、前端 `web/dist` 全部正常
- 单元测试：`332 passed, 4 skipped`（跳过的 4 个是只在 Windows 上跑的 `.bat` 检查）
- 本机 OCR：Vision 可用（6 种语言，不含中文）；tesseract 5.5.3 含 `chi_sim`，中文图识别正常
- lark-cli 1.0.98：用 Node 直接跑 `scripts/run.js` 正常
