"""配置管理：settings.yaml（非密钥）与 secrets.yaml（密钥）。

- settings.yaml 首次运行时由 settings.example.yaml 生成；读取时以样例为默认值做深合并，
  因此样例里新增的键会自动生效。
- secrets.yaml 不存在时创建，并随机生成 ``app.token``。
- ``update_settings`` / ``update_secrets`` 深合并后原子写回。
"""

from __future__ import annotations

import copy
import os
import secrets as _secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any

import yaml

from bureau.core.paths import Paths
from bureau.core.security import is_unchanged_secret, mask_secret, mask_tree

SETTINGS_SECTIONS = ("app", "sources", "llm", "pipeline", "interests", "privacy", "research", "media")


def deep_merge(base: Any, patch: Any) -> Any:
    """返回 base 与 patch 的深合并结果（不修改入参）。字典递归合并，其它类型整体替换。"""
    if isinstance(base, dict) and isinstance(patch, dict):
        out = copy.deepcopy(base)
        for k, v in patch.items():
            out[k] = deep_merge(out.get(k), v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(patch)


def get_path(tree: dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = tree
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_path(tree: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = tree
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def write_yaml_atomic(path: Path, data: dict[str, Any], header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    text = header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:          # Windows 上文件可能被短暂占用
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, path)


_SETTINGS_HEADER = "# 情报局工作台设置（不含密钥）。由程序维护，手工修改后重启服务生效。\n"
_SECRETS_HEADER = "# 情报局工作台密钥。不要提交到版本库，不要发给别人。\n"


class ConfigManager:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self._lock = threading.RLock()
        self._defaults: dict[str, Any] = {}
        self._settings: dict[str, Any] = {}
        self._secrets: dict[str, Any] = {}
        self.load()

    # ---------- 加载 ----------
    def load(self) -> None:
        with self._lock:
            self._defaults = read_yaml(self.paths.settings_example)
            if not self.paths.settings.exists():
                if self.paths.settings_example.exists():
                    shutil.copyfile(self.paths.settings_example, self.paths.settings)
                else:
                    write_yaml_atomic(self.paths.settings, {}, _SETTINGS_HEADER)
            user = read_yaml(self.paths.settings)
            self._settings = deep_merge(self._defaults, user)
            self._secrets = read_yaml(self.paths.secrets)
            if not get_path(self._secrets, "app.token"):
                set_path(self._secrets, "app.token", _secrets.token_urlsafe(24))
                self._save_secrets()

    # ---------- settings ----------
    @property
    def settings(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._settings)

    @property
    def defaults(self) -> dict[str, Any]:
        return copy.deepcopy(self._defaults)

    def get(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(get_path(self._settings, dotted, default))

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            user = read_yaml(self.paths.settings)
            user = deep_merge(user, patch)
            write_yaml_atomic(self.paths.settings, user, _SETTINGS_HEADER)
            self._settings = deep_merge(self._defaults, user)
            return copy.deepcopy(self._settings)

    # ---------- secrets ----------
    @property
    def token(self) -> str:
        with self._lock:
            return str(get_path(self._secrets, "app.token", ""))

    def secret(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(get_path(self._secrets, dotted, default))

    def secrets_tree(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._secrets)

    def update_secrets(self, patch: dict[str, Any]) -> None:
        """深合并密钥。值为空串或掩码的叶子表示不修改；值为 None 表示删除。"""
        with self._lock:
            self._secrets = _merge_secret_patch(self._secrets, patch)
            self._save_secrets()

    def delete_secret(self, dotted: str) -> None:
        with self._lock:
            parts = dotted.split(".")
            cur: Any = self._secrets
            for part in parts[:-1]:
                if not isinstance(cur, dict) or part not in cur:
                    return
                cur = cur[part]
            if isinstance(cur, dict) and parts[-1] in cur:
                del cur[parts[-1]]
                self._save_secrets()

    def secret_values(self) -> list[str]:
        """所有密钥明文（日志脱敏用）。"""
        out: list[str] = []

        def walk(x: Any) -> None:
            if isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
            elif isinstance(x, str) and len(x) >= 6:
                out.append(x)

        with self._lock:
            walk(self._secrets)
        return out

    def masked_secrets(self) -> dict[str, Any]:
        with self._lock:
            tree = copy.deepcopy(self._secrets)
        tree.pop("app", None)
        return mask_tree(tree)

    def _save_secrets(self) -> None:
        write_yaml_atomic(self.paths.secrets, self._secrets, _SECRETS_HEADER)


def _merge_secret_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict):
            cur = out.get(k)
            out[k] = _merge_secret_patch(cur if isinstance(cur, dict) else {}, v)
        elif v is None:
            out.pop(k, None)
        elif is_unchanged_secret(v):
            continue
        else:
            out[k] = v
    return out


__all__ = [
    "ConfigManager", "SETTINGS_SECTIONS", "deep_merge", "get_path", "set_path",
    "read_yaml", "write_yaml_atomic", "mask_secret", "mask_tree",
]
