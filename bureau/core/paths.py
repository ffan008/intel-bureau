"""项目路径。所有目录都基于项目根，data/ 下的子目录在 ensure() 时自动创建。

可以用环境变量覆盖（测试会用到）：
- ``BUREAU_ROOT``：项目根
- ``BUREAU_DATA_DIR``：数据目录（默认 <root>/data）
- ``BUREAU_CONFIG_DIR``：配置目录（默认 <root>/config）
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    r = Path(root or os.environ.get("BUREAU_ROOT") or PROJECT_ROOT).resolve()
    d = Path(data or os.environ.get("BUREAU_DATA_DIR") or (r / "data")).resolve()
    c = Path(config or os.environ.get("BUREAU_CONFIG_DIR") or (r / "config")).resolve()
    return Paths(root=r, data=d, config=c)
