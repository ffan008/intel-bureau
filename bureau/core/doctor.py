"""体检：列出每个平台、模型和通道的状态及修复建议。B 的模块缺失时显示"未实现"，不报错。"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import os
import socket
import sys
from typing import Any

from bureau.channels import CHANNEL_REGISTRY
from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.channel_service import kind_info
from bureau.core.constants import LIVE_PLATFORMS
from bureau.core.platform_hints import PIP_INSTALL_HINT, SETUP_CMD
from bureau.core.platforms import adapter_info, adapter_keys, check_health
from bureau.integrations.wda_auth import resolve_token


def _c(id_: str, title: str, status: str, detail: str, hint: str | None = None) -> dict[str, Any]:
    d = {"id": id_, "title": title, "status": status, "detail": detail}
    if hint:
        d["hint"] = hint
    return d


def _env_checks(app: Any) -> list[dict[str, Any]]:
    out = []
    v = sys.version_info
    out.append(_c("python", "Python", "ok" if v >= (3, 12) else "degraded", f"{v.major}.{v.minor}.{v.micro}（{sys.executable}）",
                  None if v >= (3, 12) else "建议使用 Python 3.12"))
    missing = [m for m in ("fastapi", "uvicorn", "pydantic", "httpx", "yaml", "apscheduler", "dateutil", "jieba", "tzdata")
               if importlib.util.find_spec(m) is None]
    out.append(_c("deps", "Python 依赖", "down" if missing else "ok",
                  f"缺少：{'、'.join(missing)}" if missing else "requirements.txt 中的依赖已安装",
                  PIP_INSTALL_HINT if missing else None))
    p = app.paths
    out.append(_c("config", "配置文件", "ok" if p.settings.exists() and p.secrets.exists() else "down",
                  f"{p.settings.name}、{p.secrets.name} 位于 {p.config}；访问令牌已生成" if app.config.token else "缺少访问令牌",
                  None if app.config.token else "运行 python -m bureau init"))
    db = app.db
    size = os.path.getsize(p.db) / 1024 / 1024 if p.db.exists() else 0
    n_msgs = db.scalar("SELECT COUNT(*) FROM messages", (), 0)
    n_groups = db.scalar("SELECT COUNT(*) FROM groups WHERE whitelisted=1", (), 0)
    mode = db.query_one("PRAGMA journal_mode")["journal_mode"]
    out.append(_c("database", "数据库", "ok" if db.fts_enabled else "degraded",
                  f"版本 {db.user_version}，{mode.upper()}，全文检索 {db.fts_tokenizer or '不可用'}；{size:.1f} MB，"
                  f"{n_msgs:,} 条消息，{n_groups} 个白名单群", None if db.fts_enabled else "当前 SQLite 不支持 FTS5，搜索会变慢"))
    try:
        probe = p.tmp / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        out.append(_c("data_dir", "数据目录", "ok", f"{p.data} 可写"))
    except OSError as exc:
        out.append(_c("data_dir", "数据目录", "down", f"{p.data} 不可写：{exc}", "检查目录权限"))
    has_dict = p.userdict.exists() and p.taxonomy.exists()
    out.append(_c("nlp", "分词词典与分类体系", "ok" if has_dict else "degraded",
                  "userdict.txt、taxonomy.yaml 已就绪" if has_dict else "缺少 config/dicts/userdict.txt 或 config/taxonomy.yaml",
                  None if has_dict else "从版本库恢复 config 目录"))
    return out


async def _platform_checks(app: Any) -> list[dict[str, Any]]:
    out = []
    for p in LIVE_PLATFORMS:
        label = PLATFORM_LABELS[Platform(p)]
        infos = [adapter_info(k) for k in adapter_keys(p)]
        impl = [i["key"] for i in infos if i["available"]]
        missing = [i["key"] for i in infos if not i["available"]]
        summary = f"已实现适配器：{'、'.join(impl) or '无'}" + (f"；未实现：{'、'.join(missing)}" if missing else "")
        enabled = bool(app.config.get(f"sources.{p}.enabled", False))
        adapter = app.config.get(f"sources.{p}.adapter")
        if not enabled:
            out.append(_c(f"platform.{p}", f"{label}采集", "disabled", f"未启用（{summary}）",
                          "在「情报源」页面启用并选择适配器；也可以先导入聊天记录文件"))
            continue
        h = await check_health(app, p, timeout=6)
        out.append(_c(f"platform.{p}", f"{label}采集（{adapter}）", h["state"], f"{h['detail']}（{summary}）", h.get("hint")))
    has_token = bool(resolve_token(None))
    out.append(_c("security.wda", "WeChatDataAnalysis 安全提醒", "ok" if not app.config.get("sources.wechat.enabled") else "degraded",
                  ("WeChatDataAnalysis 的本地 API 有 Token，但 Token 明文存在本机配置里，且开放了 CORS（*）"
                   if has_token else
                   "WeChatDataAnalysis 的本地 API 没有鉴权且开放了 CORS（*）"),
                  "运行期间不要打开不可信网页，不用时关掉它"))
    for mod, func, title in (("bureau.integrations.onebot", "parse_onebot_event", "QQ 实时上报解析"),
                             ("bureau.collectors.file_import", "parse_export", "聊天记录导入解析")):
        try:
            ok = hasattr(importlib.import_module(mod), func)
            out.append(_c(f"module.{func}", title, "ok" if ok else "unconfigured",
                          f"{mod}.{func} 可用" if ok else f"{mod} 缺少 {func}（未实现）"))
        except ImportError:
            out.append(_c(f"module.{func}", title, "unconfigured", f"{mod} 未实现", "对应接口会返回 501"))
        except Exception as exc:                                     # noqa: BLE001
            out.append(_c(f"module.{func}", title, "down", f"{mod} 加载出错：{exc}"))
    return out


def _llm_checks(app: Any) -> list[dict[str, Any]]:
    from bureau.llm.claude_code import find_claude
    from bureau.llm.factory import llm_status

    st = llm_status(app)
    consent = st["cloud_consent"]
    status = "ok" if not st["offline_mode"] else "degraded"
    hint = None
    if st["blocked_by_consent"]:
        hint = "在「智能体」页面打开「允许使用云端模型」后，才会把群聊内容发给云端模型"
    elif st["offline_mode"]:
        hint = "在「智能体」页面配置模型（DeepSeek / 通义 / Kimi / 智谱 / 硅基流动 / OpenRouter / Ollama 或 Claude Code）"
    out = [_c("llm", "大模型", status, f"当前使用 {st['provider']}{('（' + st['model'] + '）') if st['model'] else ''}：{st['reason']}"
              f"；云端同意：{'已同意' if consent else '未同意'}", hint)]
    exe = find_claude(str(app.config.get("llm.claude_code.command") or "claude"))
    out.append(_c("llm.claude_code", "Claude Code CLI", "ok" if exe else "unconfigured", f"已找到 {exe}" if exe else "没有找到 claude 命令",
                  None if exe else "需要时安装 Claude Code 并登录"))
    return out


def _channel_checks(app: Any) -> list[dict[str, Any]]:
    from bureau.core.channel_service import build_channel

    out = []
    for ch in app.store.list_channels():
        info = kind_info(ch["kind"])
        if not ch["enabled"]:
            out.append(_c(f"channel.{ch['id']}", f"通道：{ch['name']}", "disabled", f"{info['label']}，已停用"))
            continue
        if not info["available"]:
            out.append(_c(f"channel.{ch['id']}", f"通道：{ch['name']}", "unconfigured", f"{info['label']}：{info.get('detail', '未实现')}"))
            continue
        try:
            errors = build_channel(app, ch).validate()
        except Exception as exc:                                     # noqa: BLE001
            errors = [str(exc)]
        last = f"；最近一次：{'成功' if ch.get('last_ok') else '失败'}（{ch.get('last_at')}）" if ch.get("last_at") else ""
        out.append(_c(f"channel.{ch['id']}", f"通道：{ch['name']}", "degraded" if errors else "ok",
                      ("配置不完整：" + "；".join(errors)) if errors else f"{info['label']}，配置完整{last}",
                      "在「推送通道」页面补全配置" if errors else None))
    kinds = [kind_info(k) for k in CHANNEL_REGISTRY]
    missing = [k["kind"] for k in kinds if not k["available"]]
    out.append(_c("channel.kinds", "推送通道类型", "ok" if not missing else "degraded",
                  f"已实现 {len(kinds) - len(missing)}/{len(kinds)} 种" + (f"；未实现：{'、'.join(missing)}" if missing else "")))
    return out


def _misc_checks(app: Any) -> list[dict[str, Any]]:
    from bureau.scheduler import next_fire

    out = []
    scheds = [s for s in app.store.list_schedules() if s["enabled"]]
    nxt = min((t for t in (next_fire(s["cron"], s["timezone"], app.now()) for s in scheds) if t), default=None)
    out.append(_c("schedules", "定时任务", "ok" if scheds else "disabled",
                  f"{len(scheds)} 个已启用" + (f"，下次运行 {nxt:%m-%d %H:%M}" if nxt else ""),
                  None if scheds else "在「调度中心」添加定时任务"))
    dist = app.paths.web_dist / "index.html"
    out.append(_c("web", "前端界面", "ok" if dist.exists() else "unconfigured",
                  "web/dist 已构建" if dist.exists() else "web/dist 不存在，访问 / 会显示提示页",
                  None if dist.exists() else f"运行 {SETUP_CMD}（或在 web 目录 npm ci && npm run build）"))
    with socket.socket() as s:
        s.settimeout(0.5)
        in_use = s.connect_ex(("127.0.0.1", app.port)) == 0
    out.append(_c("port", f"端口 {app.port}", "ok", "已被占用（工作台可能已在运行）" if in_use else "空闲，可以启动服务"))
    return out


async def run_checks(app: Any) -> list[dict[str, Any]]:
    out = _env_checks(app)
    out += await _platform_checks(app)
    out += _llm_checks(app)
    out += await asyncio.to_thread(_channel_checks, app)
    out += _misc_checks(app)
    return out
