"""根目录的 .bat 启动器：双击会被 cmd 解析，一个括号写错就整个文件报错、窗口闪退，所以单独做静态检查。

规则（都是踩过的坑）：
- 只能是 ASCII（中文提示放在 .ps1 里，bat 在不同代码页下会乱码）；
- 行尾必须是 CRLF（LF 行尾会让 goto / 标签在某些情况下找不到）；
- 不用「if ... ( ... )」代码块：块里的 echo 带一个右括号就会提前结束整个块；
- 每个 goto 的标签都要存在；
- 启动脚本引用的 .ps1 要存在，或者前面有 if not exist 保护。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BATS = sorted(ROOT.glob("*.bat"))


def test_there_are_launchers():
    assert BATS, "根目录应该有 .bat 启动器"


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_bat_is_ascii_crlf_and_block_free(bat: Path):
    raw = bat.read_bytes()
    assert all(b < 128 for b in raw), f"{bat.name} 含非 ASCII 字符，不同代码页下会乱码或解析失败"
    assert b"\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), f"{bat.name} 行尾必须全是 CRLF"
    for no, line in enumerate(raw.decode("ascii").splitlines(), 1):
        t = line.strip()
        assert not t.endswith("("), f"{bat.name}:{no} 不要用括号代码块（块里一个右括号就会让整个文件解析失败）：{t}"
        assert not t.startswith(")"), f"{bat.name}:{no} 不要用括号代码块：{t}"


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_bat_labels_resolve(bat: Path):
    text = bat.read_text("ascii")
    labels = {m.group(1).lower() for m in re.finditer(r"(?m)^:([A-Za-z0-9_]+)\s*$", text)}
    for m in re.finditer(r"(?im)\bgoto\s+:?([A-Za-z0-9_]+)", text):
        target = m.group(1).lower()
        assert target == "eof" or target in labels, f"{bat.name} 的 goto {target} 没有对应标签"


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_bat_runs_to_clean_exit_without_parse_error(bat: Path):
    """真的用 cmd 跑一遍（stdin 关闭，pause 立即返回），不允许出现解析错误。只在 Windows 上运行。"""
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("只在 Windows 上检查 .bat")
    # 用一个空目录里的拷贝跑：所有依赖文件都不存在，走的是各 bat 的「找不到文件」分支，不会真的安装或启动任何东西
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / bat.name
        shutil.copy(bat, copy)
        res = subprocess.run(["cmd.exe", "/c", str(copy)], stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                             cwd=td)
    out = (res.stdout + res.stderr).decode("mbcs", errors="replace").lower()
    assert "unexpected at this time" not in out, f"{bat.name} 解析出错：{out[:200]}"
    assert "is not recognized" not in out, f"{bat.name} 调用了不存在的命令：{out[:200]}"
    assert "cannot find" in out, f"{bat.name} 在缺少文件时应该给出提示，而不是直接退出：{out[:200]}"
    assert res.returncode == 1


# ---------------------------------------------------------------- macOS：.command / .sh
#
# .command 双击时由「终端」用 /bin/bash 执行，出错就会一闪而过，所以同样做静态检查。

ROOT_CMD = sorted(ROOT.glob("*.command"))
SHELL_SCRIPTS = sorted((ROOT / "scripts").glob("*.sh"))


def test_macos_launchers_exist():
    names = {p.name for p in ROOT_CMD}
    assert {"一键安装并启动.command", "启动情报局.command", "飞书重新授权.command", "开机自启设置.command"} <= names
    scripts = {p.name for p in SHELL_SCRIPTS}
    assert {"setup.sh", "start.sh", "first-run.sh", "autostart.sh", "feishu-reauth.sh"} <= scripts


@pytest.mark.parametrize("script", ROOT_CMD + SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_script_is_lf_and_has_shebang(script: Path):
    raw = script.read_bytes()
    assert raw.startswith(b"#!"), f"{script.name} 第一行要是 shebang"
    assert b"\r\n" not in raw, f"{script.name} 必须是 LF 行尾（CRLF 会让 /bin/bash 把 \r 当成参数）"
    raw.decode("utf-8")                                  # 允许中文提示，但必须是合法 UTF-8


@pytest.mark.parametrize("script", ROOT_CMD + SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_script_is_executable(script: Path):
    import os

    if os.name == "nt":
        pytest.skip("Windows 没有可执行位")
    assert os.access(script, os.X_OK), f"{script.name} 没有执行权限（双击会失败）：chmod +x"


@pytest.mark.parametrize("cmd", ROOT_CMD, ids=lambda p: p.name)
def test_command_launchers_reference_existing_scripts(cmd: Path):
    """每个 .command 里用到的 scripts/xxx.sh 都要真的存在。"""
    import re

    for ref in re.findall(r'"?(scripts/[A-Za-z0-9_-]+\.sh)"?', cmd.read_text("utf-8")):
        assert (ROOT / ref).is_file(), f"{cmd.name} 引用的 {ref} 不存在"


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_script_syntax(script: Path):
    """bash -n：只做语法检查，不执行。"""
    import os
    import subprocess

    bash = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
    res = subprocess.run([bash, "-n", str(script)], capture_output=True, timeout=60)
    assert res.returncode == 0, f"{script.name} 语法错误：{res.stderr.decode('utf-8', 'replace')[:300]}"
