"""wda_auth：从 WeChatDataAnalysis 桌面版自己的运行配置里读 API Token（2.x 起接口要鉴权）。"""

from __future__ import annotations

import json
from pathlib import Path

from bureau.integrations.wda_auth import (candidate_runtime_files, discover, discover_token,
                                          is_loopback_url, resolve_token)


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), "utf-8")
    return path


def test_discover_token_from_default_output_dir(tmp_path):
    _write(tmp_path / "output" / "runtime_settings.json",
           {"mcp_token": "tok-abc", "selected_chat_account": "wxid_me"})
    assert discover_token(tmp_path) == "tok-abc"
    assert discover(tmp_path) == ("tok-abc", "wxid_me")


def test_output_dir_from_desktop_settings_wins(tmp_path):
    """应用里改过输出目录时，Token 在新目录里，要优先看那里。"""
    _write(tmp_path / "desktop-settings.json", {"outputDir": str(tmp_path / "elsewhere")})
    _write(tmp_path / "elsewhere" / "runtime_settings.json", {"mcp_token": "tok-2"})
    _write(tmp_path / "output" / "runtime_settings.json", {"mcp_token": "tok-1"})
    assert candidate_runtime_files(tmp_path)[0] == tmp_path / "elsewhere" / "runtime_settings.json"
    assert discover_token(tmp_path) == "tok-2"


def test_missing_file_means_no_auth(tmp_path):
    """源码版 / 开源版没有这个文件，也就没有鉴权：返回空串，请求不带鉴权头。"""
    assert discover_token(tmp_path) == ""
    assert discover(tmp_path) == ("", "")


def test_broken_json_is_ignored(tmp_path):
    p = tmp_path / "output" / "runtime_settings.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", "utf-8")
    assert discover_token(tmp_path) == ""


def test_resolve_prefers_configured_token(tmp_path):
    _write(tmp_path / "output" / "runtime_settings.json", {"mcp_token": "auto"})
    assert resolve_token("manual", tmp_path) == "manual"
    assert resolve_token("", tmp_path) == "auto"
    assert resolve_token(None, tmp_path) == "auto"


def test_is_loopback_url():
    assert is_loopback_url("http://127.0.0.1:10392")
    assert is_loopback_url("http://localhost:10392")
    assert not is_loopback_url("http://10.1.2.3:10392")
    assert not is_loopback_url("https://wda.example.com")
