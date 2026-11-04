"""命令行：python -m bureau serve | run | doctor | demo seed | demo clear | groups refresh | init"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import threading
import webbrowser
from typing import Any

STATUS_ICON = {"ok": "✔ 正常", "degraded": "▲ 降级", "down": "✘ 故障", "disabled": "○ 停用", "unconfigured": "◌ 未就绪"}
STAGE_ICON = {"done": "✔", "failed": "✘", "skipped": "–", "running": "▶"}


def setup_stdio() -> None:
    """控制台是 GBK 时也输出 UTF-8；pythonw 下没有标准输出时重定向到空设备。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _app(console: bool = False, port: int | None = None) -> Any:
    from bureau.core.app import AppContext

    return AppContext(port=port, console_log=console)


# ---------------------------------------------------------------- serve
def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from bureau.api import create_app

    ctx = _app(console=True, port=args.port)
    host = "127.0.0.1"
    with socket.socket() as s:
        if s.connect_ex((host, ctx.port)) == 0:
            print(f"端口 {ctx.port} 已被占用：工作台可能已经在运行。浏览器打开 http://{host}:{ctx.port}")
            return 1
    url = f"http://{host}:{ctx.port}"
    print(f"情报局工作台启动中：{url}（按 Ctrl+C 停止）", flush=True)
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    config = uvicorn.Config(create_app(ctx), host=host, port=ctx.port, log_config=None, access_log=False,
                            log_level="warning", lifespan="on")
    uvicorn.Server(config).run()
    ctx.close()
    return 0


# ---------------------------------------------------------------- run
async def _run(args: argparse.Namespace) -> int:
    from bureau.core.constants import STAGE_LABELS, STAGES
    from bureau.pipeline.runner import RunBusyError, RunRequest

    ctx = _app()
    platforms = [p.strip() for p in (args.platforms or "").split(",") if p.strip()]
    req = RunRequest(trigger="manual", platforms=platforms, window_hours=args.window_hours,
                     window_mode="fixed_hours" if args.window_hours else "since_last", dry_run=args.dry_run,
                     demo=args.demo, channel_ids=None)
    sub = ctx.bus.subscribe(maxsize=2000)
    printed_running: set[str] = set()

    async def printer() -> None:
        while True:
            ev = await sub.get()
            if ev is None:
                continue
            if ev.type == "run.stage":
                st = ev.data["stage"]
                name, status = st["name"], st["status"]
                idx = STAGES.index(name) + 1
                if status == "running":
                    if name not in printed_running:
                        printed_running.add(name)
                        print(f"[{idx:02d}/12] ▶ {STAGE_LABELS[name]}（{name}）…", flush=True)
                    continue
                dur = f"{st.get('duration_ms', 0) / 1000:.1f}s" if st.get("duration_ms") is not None else ""
                print(f"[{idx:02d}/12] {STAGE_ICON.get(status, '?')} {STAGE_LABELS[name]:<4} {status:<8} {dur:>6}  "
                      f"{st.get('message', '')}", flush=True)
            elif ev.type == "run.log" and ev.data.get("level") in ("warn", "error"):
                print(f"        ⚠ {ev.data['source']}：{ev.data['message']}", flush=True)

    task = asyncio.create_task(printer())
    try:
        dto = await ctx.runner.run(req)
    except RunBusyError as exc:
        print(f"无法开始：{exc}")
        return 2
    finally:
        await asyncio.sleep(0.05)
        task.cancel()
        sub.close()
    t = dto["totals"]
    print(f"\n运行 {dto['id']}：{ {'success': '成功', 'partial': '部分成功', 'failed': '失败', 'cancelled': '已取消'}[dto['status']] }"
          + (f"（{dto['error']}）" if dto.get("error") else ""))
    print(f"窗口 {dto['window_start']} ~ {dto['window_end']}；原始 {t['messages_raw']:,} → 有效 {t['messages_clean']:,}；"
          f"块 {t['chunks']}；候选 {t['candidates']}；情报 {t['items']}；引擎 {t['llm_provider'] or '—'}")
    if dto.get("report_id"):
        r = ctx.store.get_report(dto["report_id"])
        if r:
            print(f"报告：{r['title']}")
            for k, v in (r.get("files") or {}).items():
                print(f"  {k:<4} {v}")
    ctx.close()
    return 0 if dto["status"] in ("success", "partial") else 1


def cmd_run(args: argparse.Namespace) -> int:
    return asyncio.run(_run(args))


# ---------------------------------------------------------------- doctor
def print_table(rows: list[dict[str, Any]]) -> None:
    from bureau.core.textutil import display_width, pad

    w_status = 8
    w_title = min(30, max(display_width(r["title"]) for r in rows) + 2)
    line = "─" * (w_status + w_title + 60)
    print(line)
    print(pad("状态", w_status + 2) + pad("检查项", w_title) + "说明")
    print(line)
    for r in rows:
        print(pad(STATUS_ICON.get(r["status"], r["status"]), w_status + 2) + pad(r["title"], w_title) + r["detail"])
        if r.get("hint"):
            print(" " * (w_status + 2 + w_title) + f"↳ {r['hint']}")
    print(line)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("合计：" + "，".join(f"{STATUS_ICON[k].split(' ')[1]} {v}" for k, v in counts.items() if k in STATUS_ICON))


def cmd_doctor(args: argparse.Namespace) -> int:
    from bureau.core.doctor import run_checks

    ctx = _app()
    rows = asyncio.run(run_checks(ctx))
    print_table(rows)
    ctx.close()
    return 0


# ---------------------------------------------------------------- demo / groups / init
def cmd_demo(args: argparse.Namespace) -> int:
    from bureau.demo import clear_demo, seed_demo

    ctx = _app()
    if args.action == "seed":
        res = seed_demo(ctx, reset=not args.keep, scale=args.scale)
        print(f"演示数据已写入：{res['groups']} 个群（微信 4 · QQ 3 · 飞书 2），共 {res['messages']:,} 条消息（7 天）")
        print("下一步：python -m bureau run --demo --dry-run")
    else:
        res = clear_demo(ctx)
        print(f"演示数据已清除：{res['groups']} 个群，{res['reports']} 份报告")
    ctx.close()
    return 0


def cmd_groups(args: argparse.Namespace) -> int:
    from bureau.api.errors import ApiError
    from bureau.api.routes_sources import refresh_groups
    from bureau.core.constants import LIVE_PLATFORMS

    ctx = _app()
    platforms = [args.platform] if args.platform else [p for p in LIVE_PLATFORMS if ctx.config.get(f"sources.{p}.enabled")]
    if not platforms:
        print("没有启用的平台。用 --platform wechat|qq|feishu 指定，或先在「情报源」页面启用。")
    code = 0
    for p in platforms:
        try:
            res = asyncio.run(refresh_groups(ctx, p))
            print(f"{p}：新增 {res['added']}，更新 {res['updated']}，共 {res['total']} 个群")
        except ApiError as exc:
            code = 1
            print(f"{p}：{exc.message}" + (f"（{exc.hint}）" if exc.hint else ""))
    ctx.close()
    return code


def cmd_init(args: argparse.Namespace) -> int:
    ctx = _app()
    print("初始化完成：")
    print(f"  设置   {ctx.paths.settings}")
    print(f"  密钥   {ctx.paths.secrets}（访问令牌已生成，不会显示在这里）")
    print(f"  数据库 {ctx.paths.db}（版本 {ctx.db.user_version}）")
    print(f"  默认通道：{'、'.join(c['name'] for c in ctx.store.list_channels()) or '无'}；"
          f"定时任务：{'、'.join(s['name'] + ' ' + s['cron'] for s in ctx.store.list_schedules()) or '无'}")
    ctx.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m bureau", description="情报局工作台")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="启动工作台服务（127.0.0.1）")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--open", action="store_true", help="启动后打开浏览器")
    s.set_defaults(func=cmd_serve)
    r = sub.add_parser("run", help="立即运行一次流水线")
    r.add_argument("--demo", action="store_true", help="使用演示数据")
    r.add_argument("--dry-run", action="store_true", help="只生成报告，不投递")
    r.add_argument("--platforms", default="", help="逗号分隔：wechat,qq,feishu")
    r.add_argument("--window-hours", type=int, default=None, help="窗口小时数（默认自上次成功运行起）")
    r.set_defaults(func=cmd_run)
    d = sub.add_parser("doctor", help="体检")
    d.set_defaults(func=cmd_doctor)
    dm = sub.add_parser("demo", help="演示数据")
    dm.add_argument("action", choices=["seed", "clear"])
    dm.add_argument("--keep", action="store_true", help="seed 时保留已有演示数据的时间锚点")
    dm.add_argument("--scale", type=float, default=None, help="数据量倍数（默认 1.0）")
    dm.set_defaults(func=cmd_demo)
    g = sub.add_parser("groups", help="群列表")
    g.add_argument("action", choices=["refresh"])
    g.add_argument("--platform", choices=["wechat", "qq", "feishu"], default=None)
    g.set_defaults(func=cmd_groups)
    i = sub.add_parser("init", help="初始化配置与数据库")
    i.set_defaults(func=cmd_init)
    return p


def main(argv: list[str] | None = None) -> int:
    setup_stdio()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("已中断")
        return 130
