"""offline 提供方：规则提取，只摘录原文、不编造。"""

from __future__ import annotations

import asyncio

from bureau.core.paths import PROJECT_ROOT
from bureau.core.taxonomy import load_taxonomy
from bureau.core.textutil import strip_ws
from bureau.llm.offline import OfflineProvider, extract_messages
from bureau.llm.schemas import ExtractOut
from tests.factories import msg

TAX = load_taxonomy(PROJECT_ROOT / "config" / "taxonomy.yaml")


def _chat() -> list[dict]:
    ms = [
        msg(1, "分享一个我跑通的漫剧流程：第一步在即梦选「首尾帧」，上传两张图；第二步写动作描述；第三步时长选 5 秒，生成 3 次挑最好的",
            sender="阿杰", minutes=0),
        msg(2, "积分消耗怎么样", sender="小鹿", minutes=2, reply_ref="m1"),
        msg(3, "我实测一集 12 个镜头花了 360 积分，不到 30 块钱", sender="阿杰", minutes=4, reply_ref="m2"),
        msg(4, "学到了，回去试试", sender="Momo", minutes=5),
        msg(5, "出一个用虚拟卡开 ChatGPT Plus 的教程，防风控步骤都写好了，要的私信我", sender="老K", minutes=40),
        msg(6, "虚拟卡开的号上个月被封了，钱也没退", sender="七七", minutes=42, reply_ref="m5"),
        msg(7, "今天天气不错", sender="青柠", minutes=80),
        msg(8, "晚上吃什么", sender="大熊", minutes=81),
    ]
    for m in ms:
        m.thread_id = "t1" if m.id <= 4 else ("t2" if m.id <= 6 else "t3")
    return [m.as_offline() for m in ms]


def test_extracts_tutorial_and_risk_but_not_chitchat():
    out = extract_messages(_chat(), TAX)
    titles = [it["title"] for it in out["items"]]
    assert len(out["items"]) == 2, titles
    tut = next(it for it in out["items"] if "漫剧" in it["title"])
    risk = next(it for it in out["items"] if "虚拟卡" in it["title"])
    assert tut["kind"] == "教程方法" and tut["category"].startswith("03")
    assert tut["steps"][:3] == ["在即梦选「首尾帧」，上传两张图", "写动作描述", "时长选 5 秒，生成 3 次挑最好的"]
    assert "合规风险" in risk["risk_flags"] and "广告引流" in risk["risk_flags"] and risk["kind"] == "风险预警"
    assert set(tut["refs"]) >= {"m1", "m2", "m3"} and "m5" not in tut["refs"]
    assert 0 < out["noise_ratio"] < 1
    ExtractOut.model_validate(out)                                   # 输出结构与 LLM 一致


def test_offline_never_fabricates():
    msgs = _chat()
    source = strip_ws("".join(m["text"] for m in msgs))
    by_ref = {m["ref"]: m for m in msgs}
    for it in extract_messages(msgs, TAX)["items"]:
        for field in (it["title"], it["hook"], *it["steps"]):
            assert strip_ws(field) in source, field
        for part in it["summary"].rstrip("。").split("；"):
            assert strip_ws(part) in source, part
        for ev in it["evidence"]:
            assert strip_ws(ev["quote"]) in strip_ws(by_ref[ev["msg"]]["text"])


def test_offline_provider_interface():
    p = OfflineProvider({}, {}, taxonomy=TAX)
    assert not p.is_cloud and p.ready()[0]
    res = asyncio.run(p.complete_json("", "", task="extract", context={"messages": _chat()}))
    assert res.provider == "offline" and res.usage["input_tokens"] == 0 and res.cost == 0
    assert len(res.parsed["items"]) == 2
    assert asyncio.run(p.complete_json("", "", task="merge", context={"similarity": 0.8})).parsed["same"] is True
