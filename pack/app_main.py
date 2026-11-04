"""macOS 打包版入口：菜单栏常驻，后台跑工作台服务。

双击 App 后：
1. 在后台起 FastAPI（127.0.0.1:8765），数据写到 ~/Library/Application Support/IntelBureau；
2. 用 Chrome 的「应用窗口」打开大屏（没装 Chrome 就用默认浏览器）；
3. 菜单栏出现「◉」，点它可打开大屏、报告目录、数据目录、日志，或退出。

打包命令见 scripts/build-macos-app.sh。源码运行时也可以直接 `python pack/app_main.py`。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

APP_NAME = "情报局"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CRASH_LOG = "app-crash.log"


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_port(port: int, timeout: float = 60.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _port_in_use(port):
            return True
        time.sleep(0.25)
    return False


def _open_screen(url: str) -> None:
    """优先用 Chrome 的应用窗口（没有地址栏，像个原生 App）；没装 Chrome 再交给默认浏览器。"""
    if Path(CHROME).is_file():
        try:
            subprocess.Popen([CHROME, f"--app={url}", "--window-size=1560,980"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            return
        except OSError:
            pass
    webbrowser.open(url)


def _start_server(ctx) -> object:
    import uvicorn

    from bureau.api import create_app

    config = uvicorn.Config(create_app(ctx), host="127.0.0.1", port=ctx.port, log_config=None,
                            access_log=False, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="bureau-server", daemon=True).start()
    return server


def _run_menubar(ctx, server, url: str) -> None:
    from AppKit import (NSApplication, NSMenu, NSMenuItem, NSObject, NSStatusBar,
                        NSVariableStatusItemLength)

    class _Actions(NSObject):
        def openScreen_(self, _sender):
            _open_screen(url)

        def openReports_(self, _sender):
            ctx.paths.reports.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["open", str(ctx.paths.reports)])

        def openData_(self, _sender):
            subprocess.Popen(["open", str(ctx.paths.data)])

        def openLog_(self, _sender):
            log_file = ctx.paths.logs / "bureau.log"
            subprocess.Popen(["open", "-t", str(log_file if log_file.exists() else ctx.paths.logs)])

        def quitApp_(self, _sender):
            try:
                server.should_exit = True
            finally:
                NSApplication.sharedApplication().terminate_(None)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                     # Accessory：只在菜单栏，不占 Dock

    item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    item.button().setTitle_("◉")
    item.button().setToolTip_(f"{APP_NAME} · {url}")

    actions = _Actions.alloc().init()
    menu = NSMenu.alloc().init()

    def add(title: str, selector: str | None, key: str = "") -> None:
        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
        if selector:
            mi.setTarget_(actions)
        else:
            mi.setEnabled_(False)
        menu.addItem_(mi)

    add("打开大屏", "openScreen:", "o")
    add(f"服务地址 127.0.0.1:{ctx.port}", None)
    menu.addItem_(NSMenuItem.separatorItem())
    add("打开报告文件夹", "openReports:")
    add("打开数据文件夹", "openData:")
    add("查看运行日志", "openLog:")
    menu.addItem_(NSMenuItem.separatorItem())
    add(f"退出{APP_NAME}", "quitApp:", "q")
    item.setMenu_(menu)

    app.run()


def main() -> int:
    from bureau.core.app import AppContext

    ctx = None
    try:
        ctx = AppContext(console_log=False)
        url = f"http://127.0.0.1:{ctx.port}"
        if _port_in_use(ctx.port):                   # 已经有一个实例在跑：直接开窗口，别起第二个
            _open_screen(url)
            return 0
        server = _start_server(ctx)
        if not _wait_port(ctx.port):
            raise RuntimeError(f"服务没能在 60 秒内起来（端口 {ctx.port}）")
        threading.Timer(0.6, _open_screen, args=(url,)).start()
        _run_menubar(ctx, server, url)
        return 0
    except Exception:                                # noqa: BLE001  App 窗口模式下看不到 stderr，落盘
        detail = traceback.format_exc()
        try:
            base = ctx.paths.logs if ctx is not None else Path.home() / "Library" / "Logs"
            base.mkdir(parents=True, exist_ok=True)
            (base / CRASH_LOG).write_text(detail, encoding="utf-8")
        except OSError:
            pass
        sys.stderr.write(detail)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
