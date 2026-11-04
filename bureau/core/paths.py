"""项目路径。所有目录都基于项目根，data/ 下的子目录在 ensure() 时自动创建。

可以用环境变量覆盖（测试会用到）：
- ``BUREAU_ROOT``：项目根
- ``BUREAU_DATA_DIR``：数据目录（默认 <root>/data）
- ``BUREAU_CONFIG_DIR``：配置目录（默认 <root>/config）

打包成 App（PyInstaller）后，只读资源在 ``sys._MEIPASS``，可写的数据与配置改放到用户目录
（macOS ``~/Library/Application Support/IntelBureau``），并用 ``BUREAU_HOME`` 整体覆盖；
这样升级 App 不会冲掉聊天记录和报告。
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR_NAME = "IntelBureau"

DATA_SUBDIRS: tuple[str, ...] = (
    "logs", "reports", "cache", "cache/llm", "cache/jieba", "tmp", "backups", "exports",
    "inbox", "inbox/wechat", "inbox/qq", "inbox/feishu",
)


@dataclass(frozen=True)
class Paths:
    root: Path
    data: Path
    config: Path

    # ---- 数据目录 ----
    @property
    def db(self) -> Path:
        return self.data / "bureau.db"

    @property
    def logs(self) -> Path:
        return self.data / "logs"

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    @property
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def llm_cache(self) -> Path:
        return self.data / "cache" / "llm"

    @property
    def jieba_cache(self) -> Path:
        return self.data / "cache" / "jieba"

    @property
    def tmp(self) -> Path:
        return self.data / "tmp"

    @property
    def backups(self) -> Path:
        return self.data / "backups"

    @property
    def inbox(self) -> Path:
        return self.data / "inbox"

    @property
    def run_lock(self) -> Path:
        return self.data / "run.lock"

    # ---- 配置目录 ----
    @property
    def settings(self) -> Path:
        return self.config / "settings.yaml"

    @property
    def settings_example(self) -> Path:
        return self.config / "settings.example.yaml"

    @property
    def secrets(self) -> Path:
        return self.config / "secrets.yaml"

    @property
    def prompts(self) -> Path:
        return self.config / "prompts"

    @property
    def taxonomy(self) -> Path:
        return self.config / "taxonomy.yaml"

    @property
    def taxonomy_v2(self) -> Path:
        """v2 新增的风险类别与词表（可选；缺失时用代码里的默认值）。"""
        return self.config / "taxonomy_v2.yaml"

    @property
    def demo_media(self) -> Path:
        return self.data / "demo_media"

    @property
    def media_cache(self) -> Path:
        """流水线取回的群图片和文件（按日期分子目录）。"""
        return self.data / "cache" / "media"

    @property
    def userdict(self) -> Path:
        return self.config / "dicts" / "userdict.txt"

    @property
    def stopwords(self) -> Path:
        return self.config / "dicts" / "stopwords.txt"

    # ---- 其它 ----
    @property
    def web_dist(self) -> Path:
        return self.root / "web" / "dist"

    def inbox_for(self, platform: str) -> Path:
        return self.inbox / platform

    def report_dir(self, day: str) -> Path:
        d = self.reports / day
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure(self) -> "Paths":
        self.data.mkdir(parents=True, exist_ok=True)
        for sub in DATA_SUBDIRS:
            (self.data / sub).mkdir(parents=True, exist_ok=True)
        self.config.mkdir(parents=True, exist_ok=True)
        return self


def resolve_paths(root: str | Path | None = None, data: str | Path | None = None,
                  config: str | Path | None = None) -> Paths:
    if is_frozen() and not root and not os.environ.get("BUREAU_ROOT"):
        res = resource_root()
        home = app_support_dir()
        c = Path(config or os.environ.get("BUREAU_CONFIG_DIR") or (home / "config"))
        seed_user_config(res, c)
        d = Path(data or os.environ.get("BUREAU_DATA_DIR") or (home / "data"))
        return Paths(root=res, data=d.expanduser().resolve(), config=c.expanduser().resolve())
    r = Path(root or os.environ.get("BUREAU_ROOT") or PROJECT_ROOT).resolve()
    d = Path(data or os.environ.get("BUREAU_DATA_DIR") or (r / "data")).resolve()
    c = Path(config or os.environ.get("BUREAU_CONFIG_DIR") or (r / "config")).resolve()
    return Paths(root=r, data=d, config=c)


def is_frozen() -> bool:
    """是否是 PyInstaller 打出来的独立 App。"""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """只读资源根：打包版是解包目录，源码版是项目根。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return PROJECT_ROOT


def app_support_dir() -> Path:
    """打包版的用户目录（数据 + 配置），可用 BUREAU_HOME 指定到别处（比如放到移动硬盘）。"""
    env = os.environ.get("BUREAU_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def seed_user_config(res: Path, dest: Path) -> None:
    """首次启动把随包的 config（提示词、词典、示例配置）铺到用户目录；之后只补缺失的文件。

    secrets.yaml / settings.yaml 是用户自己的东西，永远不覆盖。
    """
    src = res / "config"
    if not src.is_dir():
        return
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for item in src.iterdir():
        if item.name in ("secrets.yaml", "settings.yaml"):
            continue
        target = dest / item.name
        if target.exists():
            continue
        try:
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        except OSError:
            continue
