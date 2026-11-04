"""测试公共夹具：每个测试使用独立的 data/ 与 config/ 临时目录，不污染项目数据。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bureau.core.logging import setup_logging, shutdown_logging  # noqa: E402
from bureau.core.paths import Paths  # noqa: E402

CONFIG_SRC = ROOT / "config"


@pytest.fixture(scope="session", autouse=True)
def _session_logging(tmp_path_factory: pytest.TempPathFactory):
    setup_logging(tmp_path_factory.mktemp("logs"))
    yield
    shutdown_logging()


@pytest.fixture(scope="session", autouse=True)
def _no_demo_pacing():
    """大屏演示运行会按 app.demo_stage_min_ms 放慢每个阶段；测试里关掉（子进程也会继承）。"""
    old = os.environ.get("BUREAU_DEMO_PACE_MS")
    os.environ["BUREAU_DEMO_PACE_MS"] = "0"
    yield
    if old is None:
        os.environ.pop("BUREAU_DEMO_PACE_MS", None)
    else:
        os.environ["BUREAU_DEMO_PACE_MS"] = old


def make_paths(base: Path) -> Paths:
    cfg = base / "config"
    shutil.copytree(CONFIG_SRC, cfg, ignore=shutil.ignore_patterns("settings.yaml", "secrets.yaml"))
    return Paths(root=ROOT, data=base / "data", config=cfg).ensure()


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return make_paths(tmp_path)


@pytest.fixture
def app(paths: Paths):
    from bureau.core.app import AppContext

    ctx = AppContext(paths)
    yield ctx
    ctx.close()


@pytest.fixture
def demo_app(app):
    """写入小规模演示数据的应用上下文。"""
    from bureau.demo import seed_demo

    seed_demo(app, scale=0.35)
    return app
