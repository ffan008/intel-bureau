"""提示词模板：config/prompts/{extract,compose,merge}.md。

文件用 ``<!-- system -->`` 和 ``<!-- user -->`` 分成两段；``{{name}}`` 占位符由代码替换。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bureau.llm.base import INJECTION_GUARD

# v1 的三个模板仍保留（v1 服务在读）；v2 的流水线读后四个新文件（docs/V2_KNOWLEDGE.md §9）
PROMPT_NAMES = ("extract", "compose", "merge", "extract_v2", "article", "digest", "research_queries")
REQUIRED: dict[str, tuple[str, ...]] = {
    "extract": ("{{chat_log}}",),
    "compose": ("{{data}}",),
    "merge": ("{{pair}}",),
    "extract_v2": ("{{chat_log}}",),
    "article": ("{{data}}",),
    "digest": ("{{data}}",),
    "research_queries": ("{{data}}",),
}
# v2 模板缺失时退回的旧模板（避免系统提示为空）
FALLBACK: dict[str, str] = {"extract_v2": "extract"}
_SPLIT = re.compile(r"<!--\s*(system|user)\s*-->", re.I)


def prompt_path(prompts_dir: Path, name: str) -> Path:
    if name not in PROMPT_NAMES:
        raise KeyError(name)
    return prompts_dir / f"{name}.md"


def load_prompt(prompts_dir: Path, name: str) -> str:
    p = prompt_path(prompts_dir, name)
    if p.exists():
        return p.read_text(encoding="utf-8")
    if name in FALLBACK:
        return load_prompt(prompts_dir, FALLBACK[name])
    return ""


def prompt_exists(prompts_dir: Path, name: str) -> bool:
    return prompt_path(prompts_dir, name).exists()


def validate_prompt(name: str, content: str) -> list[str]:
    errors = []
    for token in REQUIRED.get(name, ()):
        if token not in content:
            errors.append(f"缺少占位符 {token}")
    if "<!-- user -->" not in content.replace("<!--user-->", "<!-- user -->"):
        errors.append("缺少 <!-- user --> 分段标记")
    return errors


def save_prompt(prompts_dir: Path, name: str, content: str) -> None:
    p = prompt_path(prompts_dir, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.replace("\r\n", "\n"), encoding="utf-8")


def render_prompt(prompts_dir: Path, name: str, values: dict[str, Any]) -> tuple[str, str]:
    """返回 (system, user)。系统提示末尾总会追加提示词注入防护声明。"""
    raw = load_prompt(prompts_dir, name)
    system, user = raw, ""
    parts = _SPLIT.split(raw)
    if len(parts) >= 3:
        sections: dict[str, str] = {}
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i].lower()] = parts[i + 1]
        system, user = sections.get("system", ""), sections.get("user", "")
    for k, v in values.items():
        token = "{{" + k + "}}"
        system = system.replace(token, str(v))
        user = user.replace(token, str(v))
    system = system.strip() + "\n\n" + INJECTION_GUARD
    return system, user.strip()
