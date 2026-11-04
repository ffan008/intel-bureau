"""只读探测各采集器在本机的状态：health 与 list_groups（不拉消息、不发消息、不改任何账号状态）。

用法（项目根目录）：
    .venv\\Scripts\\python.exe -X utf8 scripts\\tools\\probe_sources.py [--show-names]

默认只打印群的数量；加 --show-names 才打印群名（只在你自己的终端里显示）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bureau.collectors import create_collector  # noqa: E402
from bureau.collectors.base import CollectorContext  # noqa: E402
from bureau.contracts import Platform  # noqa: E402

PROBES = [
    ("feishu.lark_cli", Platform.FEISHU, {"identity": "bot"}, True),
    ("feishu.lark_cli", Platform.FEISHU, {"identity": "user"}, True),
    ("qq.onebot", Platform.QQ, {}, False),
    ("wechat.wda", Platform.WECHAT, {}, False),
    ("wechat.weflow", Platform.WECHAT, {}, False),
]


async def probe(key: str, platform: Platform, settings: dict, list_groups: bool, show: bool) -> None:
    ctx = CollectorContext(platform=platform, settings=settings, secrets={}, data_dir=ROOT / "data")
    c = create_collector(key, ctx)
    tag = f"{key}" + (f"（identity={settings['identity']}）" if "identity" in settings else "")
    h = await c.health()
    print(f"\n[{tag}] health：{h.state.value}  ok={h.ok}")
    print(f"  detail：{h.detail}")
    if h.hint:
        print(f"  hint：{h.hint}")
    if list_groups:
        try:
            groups = await c.list_groups()
            print(f"  list_groups：{len(groups)} 个群")
            if show:
                for g in groups:
                    print(f"    - {g.name}（{g.native_id}）")
        except Exception as exc:  # noqa: BLE001
            print(f"  list_groups 失败：{exc}")
    await c.aclose()


async def main(show: bool) -> None:
    for key, platform, settings, lg in PROBES:
        await probe(key, platform, settings, lg, show)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="只读探测本机采集器状态")
    ap.add_argument("--show-names", action="store_true", help="打印群名")
    asyncio.run(main(ap.parse_args().show_names))
