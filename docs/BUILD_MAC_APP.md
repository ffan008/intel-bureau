# 打包成 macOS 安装包

打成 `.app` + `.dmg` 后，双击就能用，不需要终端、不需要装 Python。

## 一条命令

```bash
bash scripts/build-macos-app.sh
```

| 参数 | 作用 |
|---|---|
| （无） | 构建前端 → 打包 → 生成 dmg，全流程 |
| `--skip-web` | 跳过 `npm run build`（`web/dist` 已是最新时省 30 秒） |
| `--no-dmg` | 只出 `.app`，不做 dmg |

产物：

```
dist-app/情报局.app                    约 75 MB
dist-app/情报局-1.0.0-arm64.dmg        约 41 MB
```

## 打出来的 App 是什么样

- **菜单栏常驻**：装好后菜单栏出现「◉」，不占 Dock、不进 ⌘Tab（`LSUIElement`）。
  点它有：打开大屏 / 打开报告文件夹 / 打开数据文件夹 / 查看运行日志 / 退出。
- **双击自动开大屏**：优先用 Chrome 的 `--app` 应用窗口（无地址栏，像原生应用），没装 Chrome 就退到默认浏览器。
- **只监听 127.0.0.1:8765**，和源码版一致。
- **数据不放在 App 里**，而是在：

  ```
  ~/Library/Application Support/IntelBureau/
      config/     settings.yaml、secrets.yaml（密钥）、prompts/、dicts/
      data/       bureau.db、reports/、logs/、cache/、inbox/
  ```

  升级 App、覆盖安装、甚至删掉 App 都不会动这些数据。想彻底清空就手动删这个目录。
  想换位置（比如放移动硬盘）可以设环境变量 `BUREAU_HOME=/path/to/dir`。

## 为什么安装包只有 75 MB，而项目目录有 800 MB+

| 内容 | 是否进包 | 原因 |
|---|---|---|
| Python 运行时 + 依赖 + 前端 | ✅ 约 75 MB | 这是程序本体 |
| `third_party/tools/wda`（382 MB） | ❌ | WeChatDataAnalysis 是独立桌面应用，有自己的安装器，塞进来也不会用 |
| `third_party/tools/napcat`（34 MB） | ❌ | 同上，QQ 的 OneBot 实现 |
| `third_party/tools/lark-cli`（94 MB） | ❌ | 需要 Node 运行时；飞书采集不装也能用其它平台 |
| `data/`（聊天记录、报告） | ❌ | 用户自己的数据，不该跟着安装包走 |

所以安装包里采微信 / QQ 要在外面再装采集工具，装完回「情报源」页点「测试连接」即可。
dmg 里附了一份 `首次打开请先看这里.txt` 说明这件事。

## 打包踩过的坑（改 spec 时注意）

1. **动态导入的模块静态分析找不到**。采集器（`COLLECTOR_REGISTRY`）、推送通道（`CHANNEL_REGISTRY`）、
   `bureau.research` / `bureau.media` 都是「模块路径字符串 + `importlib`」懒加载，PyInstaller 扫不到。
   现象是打包后跑流水线报「采集器 demo.synthetic 尚未实现（缺少模块 …）」。
   现在 spec 里用 `collect_submodules("bureau")` 整包收，并从两个注册表按需补齐。
2. **jieba 会自动带上 25 MB 无用模型**。PyInstaller 自带的 `hook-jieba` 把 `lac_small`（深度学习模型）、
   `posseg` 全收了。项目只做分词 + TF-IDF，spec 里在 `Analysis` 之后过滤，只留 `dict.txt` 和 `analyse/idf.txt`。
3. **sourcemap 占 2.4 MB**。前端 `.map` 对生产无用，`add_tree` 里按后缀跳过。
4. **数据目录会写进 App 包**。`PROJECT_ROOT` 在打包后指向解包临时目录，直接用会导致重启丢数据。
   `bureau/core/paths.py` 里加了 `is_frozen()` 分支，改写到 `~/Library/Application Support`。

## 签名与公证

现在用的是 **ad-hoc 签名**（PyInstaller 自动做的），够本机用，但把 dmg 发给别人下载后，
首次打开会被 Gatekeeper 拦住（「无法验证开发者」）。用户按 dmg 里的说明右键「打开」即可放行一次。

要彻底免掉这一步，需要 Apple 开发者账号（$99/年）做 Developer ID 签名 + 公证：

```bash
codesign --deep --force --options runtime --sign "Developer ID Application: 你的名字 (TEAMID)" "dist-app/情报局.app"
xcrun notarytool submit "dist-app/情报局-1.0.0-arm64.dmg" --apple-id ... --team-id ... --password ... --wait
xcrun stapler staple "dist-app/情报局-1.0.0-arm64.dmg"
```

## 验证打包结果

```bash
# 用隔离目录跑，不污染正式数据
BUREAU_HOME=/tmp/bureau-test ./dist-app/情报局.app/Contents/MacOS/IntelBureau
curl -s http://127.0.0.1:8765/api/health
```

完整验证一次流水线（含 jieba 分词、报告渲染）：

```bash
TOK=$(curl -s http://127.0.0.1:8765/api/session | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")
curl -s -X POST http://127.0.0.1:8765/api/runs -H "X-Bureau-Token: $TOK" \
     -H "Content-Type: application/json" -d '{"demo":true,"dry_run":true}'
```

12 个阶段全部 `done` 才算打包成功。

## Windows 安装包

`pack/intelbureau.spec` 是跨平台的，在 Windows 上装好 PyInstaller 后同样能跑，
但 `EXE/BUNDLE` 那段是 macOS 专用（`BUNDLE` 只在 macOS 生效），Windows 直接得到
`dist/IntelBureau/IntelBureau.exe` 目录，再用 Inno Setup 或 NSIS 做安装器。

注意 Windows 版入口要换：`pack/app_main.py` 里的菜单栏是 AppKit（macOS 专有），
Windows 应该用一个托盘库（pystray）或者干脆保留 `.bat` 启动器 + 控制台窗口。
