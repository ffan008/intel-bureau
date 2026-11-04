"""读取 WeChatDataAnalysis 桌面版的本地 API Token。

2.x 桌面版（含高级版）的本地服务默认要求 ``Authorization: Bearer <API Token>``，否则业务接口返回
``401 {"detail":{"code":"external_token_required"}}``。Token 由应用自己生成，存在它的运行配置里，
不需要用户手抄：

- macOS：``~/Library/Application Support/wechat-data-analysis-desktop/output/runtime_settings.json``
- Windows：``%APPDATA%\\wechat-data-analysis-desktop\\output\\runtime_settings.json``

同一个文件里还有 ``selected_chat_account``（当前选中的微信账号）。

查找顺序：
1. 设置里手填的 Token（``sources.wechat.wda.token``，存 secrets.yaml）—— 优先；
2. ``<outputDir>/runtime_settings.json``，``outputDir`` 取 ``desktop-settings.json`` 里配置的值；
3. 默认输出目录下的 ``runtime_settings.json``。

开源版 / 源码版没有这个文件，也就没有鉴权，此时返回空串，请求不带鉴权头照旧可用。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger("bureau.wda")

APP_DIR_NAME = "wechat-data-analysis-desktop"
SETTINGS_FILE = "desktop-settings.json"
RUNTIME_FILE = "runtime_settings.json"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def is_loopback_url(url: str) -> bool:
    """地址是不是本机（自动读到的 Token 只往本机发，避免把本地凭据送到别的机器）。"""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS


def app_config_dir() -> Path:
    """应用的用户数据目录（Electron 的 userData）。"""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    return Path.home() / "Library" / "Application Support" / APP_DIR_NAME


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def candidate_runtime_files(root: Path | None = None) -> list[Path]:
    """可能藏着 Token 的 runtime_settings.json，按优先级排好。"""
    root = root or app_config_dir()
    out: list[Path] = []
    output_dir = str(_read_json(root / SETTINGS_FILE).get("outputDir") or "").strip()
    if output_dir:
        out.append(Path(output_dir) / RUNTIME_FILE)
    default = root / "output" / RUNTIME_FILE
    if default not in out:
        out.append(default)
    return out


def _from_files(files: list[Path]) -> tuple[str, str]:
    for f in files:
        data = _read_json(f)
        token = str(data.get("mcp_token") or data.get("apiToken") or data.get("api_token") or "").strip()
        if token:
            account = str(data.get("selected_chat_account") or "").strip()
            return token, account
    return "", ""


def discover_token(root: Path | None = None) -> str:
    """自动读取本机应用的 API Token；读不到返回空串（老版本没有鉴权）。"""
    token, _ = _from_files(candidate_runtime_files(root))
    return token


def discover(root: Path | None = None) -> tuple[str, str]:
    """(token, 当前选中的微信账号)；都读不到时为空串。"""
    return _from_files(candidate_runtime_files(root))


def resolve_token(configured: str | None, root: Path | None = None) -> str:
    """设置里填了就用设置的，否则自动读本机应用。"""
    explicit = str(configured or "").strip()
    return explicit or discover_token(root)
