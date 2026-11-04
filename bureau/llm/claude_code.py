"""claude_code 提供方：调用本机 ``claude`` CLI。

参数已用 ``claude --help``（2.1.312）核对：``-p --output-format json --no-session-persistence --tools ""
--strict-mcp-config --disable-slash-commands --system-prompt ... [--json-schema ...] [--model ...]``。
提示词走 stdin（Windows 命令行有长度上限），在空的临时目录里运行，超时默认 180 秒。
输出 JSON 的 ``result`` 是文本，用 ``--json-schema`` 时 ``structured_output`` 是解析好的对象。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from bureau.llm.base import LLMError, LLMProvider, LLMResult

_SEMAPHORES: dict[int, asyncio.Semaphore] = {}


def find_claude(command: str = "claude") -> str | None:
    """找到 claude 可执行文件。npm 安装时 PATH 上是 .cmd/.ps1 包装，优先换成真正的 claude.exe。"""
    p = Path(command)
    if p.is_absolute() and p.exists():
        return str(p)
    found = shutil.which(command)
    if not found:
        return None
    fp = Path(found)
    if fp.suffix.lower() in (".cmd", ".ps1", ".bat", "") and os.name == "nt":
        exe = fp.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.exists():
            return str(exe)
        cmd = fp.with_suffix(".cmd")
        if cmd.exists():
            return str(cmd)
    return str(fp)


class ClaudeCodeProvider(LLMProvider):
    name = "claude_code"
    label = "Claude Code CLI（本机）"

    @property
    def concurrency(self) -> int:
        return max(1, int(self.cfg.get("concurrency") or 2))

    @property
    def model(self) -> str:
        return str(self.cfg.get("model") or "")

    @property
    def exe(self) -> str | None:
        return find_claude(str(self.cfg.get("command") or "claude"))

    def ready(self) -> tuple[bool, str]:
        exe = self.exe
        if not exe:
            return False, "没有找到 claude 命令"
        return True, f"已找到 {exe}"

    def _sem(self) -> asyncio.Semaphore:
        loop_id = id(asyncio.get_running_loop())
        sem = _SEMAPHORES.get(loop_id)
        if sem is None:
            sem = asyncio.Semaphore(self.concurrency)
            _SEMAPHORES[loop_id] = sem
        return sem

    def build_args(self, exe: str, system: str, schema: dict[str, Any] | None) -> list[str]:
        args = [exe, "-p", "--output-format", "json", "--no-session-persistence", "--tools", "",
                "--strict-mcp-config", "--disable-slash-commands", "--system-prompt", system]
        if schema and self.cfg.get("use_json_schema", True):
            args += ["--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":"))]
        if self.model:
            args += ["--model", self.model]
        return args

    async def complete_json(self, system: str, user: str, schema: dict[str, Any] | None = None, *,
                            max_tokens: int = 4096, temperature: float = 0.2, task: str | None = None,
                            context: dict[str, Any] | None = None) -> LLMResult:
        exe = self.exe
        if not exe:
            raise LLMError("没有找到 claude 命令", hint="安装 Claude Code（npm i -g @anthropic-ai/claude-code）后执行 claude 登录")
        timeout = float(self.cfg.get("timeout_sec") or 180)
        args = self.build_args(exe, system, schema)
        async with self._sem():
            t0 = time.perf_counter()
            proc = await asyncio.to_thread(self._run, args, user, timeout)
            latency = time.perf_counter() - t0
        return self.parse_output(proc.stdout, proc.stderr, proc.returncode, latency)

    def _run(self, args: list[str], user: str, timeout: float) -> subprocess.CompletedProcess[str]:
        base = str(self.tmp_dir) if self.tmp_dir else None
        with tempfile.TemporaryDirectory(prefix="claude-", dir=base) as cwd:
            try:
                return subprocess.run(args, input=user, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", cwd=cwd, timeout=timeout,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"claude 调用超时（{timeout:.0f} 秒）", retryable=True) from exc
            except OSError as exc:
                raise LLMError(f"无法启动 claude：{exc}", hint="检查 llm.claude_code.command 设置") from exc

    def parse_output(self, stdout: str, stderr: str, returncode: int, latency: float) -> LLMResult:
        try:
            data = json.loads(stdout or "")
        except ValueError:
            msg = (stderr or stdout or "").strip().splitlines()
            raise LLMError(f"claude 输出无法解析（退出码 {returncode}）：{(msg[-1] if msg else '')[:200]}",
                           hint="在终端里运行 claude 确认已登录") from None
        if data.get("is_error") or data.get("subtype") not in (None, "success"):
            raise LLMError(f"claude 返回错误：{str(data.get('result') or data.get('subtype'))[:200]}",
                           hint="确认已登录且额度充足", retryable=True)
        usage = data.get("usage") or {}
        tin = int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0) + \
            int(usage.get("cache_read_input_tokens") or 0)
        tout = int(usage.get("output_tokens") or 0)
        model = next(iter((data.get("modelUsage") or {}).keys()), self.model or "claude").strip()
        text = data.get("result") or ""
        parsed = data.get("structured_output")
        if parsed is not None and not text:
            text = json.dumps(parsed, ensure_ascii=False)
        return LLMResult(text=text, parsed=parsed, usage={"input_tokens": tin, "output_tokens": tout},
                         cost=round(float(data.get("total_cost_usd") or 0) * self.fx, 4), provider=self.name,
                         model=model, latency=latency)
