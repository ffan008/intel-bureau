"""平台相关的提示文案。

同一个问题，Windows 和 macOS 要告诉用户不同的命令。集中在这里，避免在日志和界面里
出现「请运行 scripts\\setup.ps1」这种在 Mac 上照着做不了的提示。
"""

from __future__ import annotations

import os
import sys

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

# 安装 / 修复依赖
SETUP_CMD = r"scripts\setup.ps1" if IS_WINDOWS else "scripts/setup.sh"
SETUP_HINT = (f"运行 {SETUP_CMD}" if IS_WINDOWS
              else "运行 bash scripts/setup.sh（或双击「一键安装并启动.command」）")

# 缺少 lark-cli
LARK_CLI_INSTALL = ("运行 scripts\\tools\\get-lark-cli.ps1 安装" if IS_WINDOWS
                    else "运行 npm i -g @larksuite/cli 安装")

# 缺少 python 依赖
PIP_INSTALL_HINT = (r"运行 scripts\setup.ps1 或 pip install -r requirements.txt" if IS_WINDOWS
                    else "运行 bash scripts/setup.sh 或 pip install -r requirements.txt")
