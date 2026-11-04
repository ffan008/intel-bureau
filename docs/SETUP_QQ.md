# QQ 接入指南

QQ 通过 **NapCatQQ** 接入：它借用你电脑上已装的 QQ NT，对外提供 OneBot 11 接口。
工作台用这个接口**读取**群消息，也可以用它把日报**私聊发给你的主号**。

## 一、先想清楚：用小号

NapCat 是非官方的客户端框架，**存在被腾讯风控（限制登录、冻结）的可能**。

1. 准备一个「情报员小号」，只用来登录 NapCat。
2. 用小号加入你想监控的群。
3. 主号**不要**登录 NapCat。主号想收日报，就让小号私聊主号（见第六步）。
4. 不要让小号做自动加群、自动回复、频繁发消息这类事。工作台只读消息，推送也只发给你自己。

## 二、下载 NapCat

> **分享包用户**：NapCat已经随包带好，**不用运行下面的下载命令**。直接双击根目录的「安装接入工具.bat」，选 2 即可。下面的命令只在你想联网更新到最新版时才需要。

在项目根目录打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tools\get-napcat.ps1
```

脚本会下载 NapCat 最新版 `NapCat.Shell.zip`，核对官方 SHA-256 后解压到
`third_party\tools\napcat\<版本>\Shell\`。需要一键包时加 `-OneKey`。

## 三、启动并用小号登录

1. 打开 `third_party\tools\napcat\<版本>\Shell\`。
2. Windows 11 双击 `launcher-user.bat`，Windows 10 双击 `launcher-win10-user.bat`。
3. 会弹出命令行窗口，并调起本机 QQ。用**小号**扫码登录。
4. 命令行里会打印 WebUI 的地址和登录令牌（令牌也保存在 Shell 目录的 `config\webui.json` 的 `token` 字段）。

## 四、在 WebUI 里配置 HTTP 服务端（必做）

1. **先改监听地址（安全）**：NapCat 的 WebUI 默认监听 `0.0.0.0`，同一局域网的设备都能访问。
   打开 Shell 目录下的 `config\webui.json`，把 `"host": "0.0.0.0"` 改成 `"host": "127.0.0.1"`，
   然后关掉 NapCat 再重新启动。
2. 浏览器打开 `http://127.0.0.1:6099`，用第三步的令牌登录。
3. 生成一个随机 token，在 PowerShell 里运行：
   ```powershell
   [guid]::NewGuid().ToString('N')
   ```
   复制输出，下面两处都要用。
4. 进入「网络配置」→ 新建 →「HTTP 服务器」：
   | 项目 | 填写 |
   |---|---|
   | 名称 | bureau |
   | 启用 | 打开 |
   | 主机 | `127.0.0.1` |
   | 端口 | `3010` |
   | 消息格式 | `array` |
   | Token | 第 3 步生成的 token |
   | CORS、WebSocket | 关闭 |
5. 保存。

## 五、可选：开启实时上报

不开也能用：定时任务会按时间窗口回溯历史消息。开了以后，新消息会实时推到工作台大屏。

1. WebUI →「网络配置」→ 新建 →「HTTP 客户端」：
   | 项目 | 填写 |
   |---|---|
   | 名称 | bureau-ingest |
   | 启用 | 打开 |
   | URL | `http://127.0.0.1:8765/api/ingest/onebot` |
   | 消息格式 | `array` |
   | 上报自身消息 | 关闭 |
   | Token | 与第四步**相同**的 token |
2. 保存。NapCat 会用这个 token 给每次上报签名（请求头 `X-Signature: sha1=…`），工作台据此校验来源。
3. 工作台只接受本机发来的上报，非白名单群的消息直接丢弃，不会保存。

配置也可以对照 `scripts\tools\napcat-config-template.json`（NapCat 的 `onebot11_<QQ号>.json` 结构）。

## 六、在工作台里填写配置

1. 工作台 →「情报源」→ QQ，适配器选 **NapCatQQ（OneBot 11）**。
2. 填写：
   | 项目 | 填写 |
   |---|---|
   | OneBot HTTP 地址 | `http://127.0.0.1:3010` |
   | Token | 第四步的 token |
   | 上报签名密钥 | 留空（与 Token 相同时不用填） |
3. 点「测试」，看到「已连接 NapCat，登录账号 情报员（QQ 号）」即成功。
4. 点「刷新群列表」，把要监控的群加入白名单。

| 提示 | 原因 | 怎么办 |
|---|---|---|
| 连不上 NapCat 的 OneBot HTTP 服务 | NapCat 没启动，或没建 HTTP 服务器，或端口不对 | 回到第三、四步 |
| NapCat 拒绝访问：token 不正确 | 工作台和 NapCat 的 token 不一致 | 重新复制 token |
| QQ 尚未登录 | 小号掉线 | 重新扫码登录 |
| NapCat 找不到更早的消息 | 本机 QQ 只保存了这么多历史 | 正常现象；开启实时上报可避免遗漏 |

## 七、主号怎么收日报

1. 用小号加主号为好友（**必须互为好友**，否则私聊会失败）。
2. 工作台 →「推送」→ 新增通道 →「QQ（NapCat OneBot）」：
   - OneBot HTTP 地址、Token：与第六步相同
   - 发送到：私聊
   - QQ 号：你的**主号** QQ 号
3. 点「发送测试」，主号应收到一条「情报局通道测试」。
4. 日报会按每段不超过 1500 字发送，最多 6 段，段间隔 1.5 秒；超出部分请在工作台查看。

也可以发到群：「发送到」选群聊，填群号（小号要在群里，且没有被禁言）。