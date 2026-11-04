"""评分、趋势、选择与证据校验。"""

from __future__ import annotations

from bureau.pipeline.score import classify_trend, memory_similarity, select, total_score
from bureau.pipeline.verify import quote_in, verify_item
from tests.factories import item, msg

W = {"novelty": 1.0, "actionability": 1.2, "credibility": 1.0, "heat": 0.9, "relevance": 1.1}
FULL = {k: 5.0 for k in W}
MID = {k: 2.5 for k in W}


def test_total_score_weights_and_penalties():
    assert total_score(FULL, W, [], "new", 0.6, 1.2) == 100.0
    assert total_score(MID, W, [], "new", 0.6, 1.2) == 50.0
    assert total_score(MID, W, ["合规风险"], "new", 0.6, 1.2) == 38.0          # 2.5 - 0.6 = 1.9
    assert total_score(MID, W, [], "repeat", 0.6, 1.2) == 26.0                # 2.5 - 1.2 = 1.3
    assert total_score(MID, W, ["a", "b", "c", "d", "e"], "new", 0.6, 1.2) == 10.0   # 风险惩罚封顶 2.0
    assert total_score({k: 0.0 for k in W}, W, ["合规风险"], "repeat", 0.6, 1.2) == 0.0


def test_trend_classification_against_memory():
    mem = {"id": 1, "title": "公众号流量主收益复盘", "keywords": ["公众号", "流量主", "阅读", "收入", "教程", "选题"], "links": []}
    same = item("公众号流量主收益复盘", core=["公众号", "流量主", "阅读", "收入", "教程"],
                keywords={"公众号", "流量主", "阅读", "收入", "教程"})
    grow = item("公众号第二个月：漫剧教程爆了", core=["公众号", "流量主", "漫剧", "标题", "爆款", "阅读"],
                keywords={"公众号", "流量主", "漫剧", "标题", "爆款", "阅读", "第二个月"})
    other = item("ComfyUI 显存优化", core=["comfyui", "显存", "flux", "fp8"], keywords={"comfyui", "显存", "flux", "fp8"})
    assert classify_trend(same, mem, memory_similarity(same, mem)) == "repeat"
    assert classify_trend(grow, mem, memory_similarity(grow, mem)) == "developing"
    assert classify_trend(other, mem, memory_similarity(other, mem)) == "new"
    assert classify_trend(other, None, 0.0) == "new"


def test_select_headlines_skip_serious_risk_and_rank_sequential():
    its = []
    for i, (score, risks, trend) in enumerate([(90, ["广告引流"], "new"), (80, [], "new"), (70, [], "repeat"), (60, [], "new"),
                                               (50, ["未核实"], "new"), (40, [], "developing"), (30, [], "new")]):
        it = item(f"情报{i}", steps=["第一步"] if i % 2 else [], evidence=[{"msg": "m1"}] * 2)
        it.score, it.risk_flags, it.trend, it.id = score, list(risks), trend, f"i{i}"
        its.append(it)
    select(its, top_n=5, max_features=3)
    assert [it.rank for it in its] == list(range(1, 8))
    heads = [it.title for it in its if it.is_headline]
    assert heads == ["情报1", "情报3", "情报4", "情报5", "情报6"]           # 跳过广告引流与重复
    assert sum(it.is_feature for it in its) == 3
    assert not any(it.is_headline for it in its if "广告引流" in it.risk_flags)


def test_quote_matching_rules():
    src = "第一步在即梦选「首尾帧」，上传起始和结束两张图；第二步写动作描述"
    assert quote_in("第一步在即梦选「首尾帧」，上传起始和结束两张图", src)
    assert quote_in("第一步在即梦选 「首尾帧」，上传起始和 结束两张图", src)          # 忽略空白
    assert quote_in("第一步在即梦选「首尾帧」……第二步写动作描述", src)               # 省略号分段
    assert not quote_in("第一步在可灵选首尾帧", src)
    assert not quote_in("", src)


def test_verify_item_relinks_drops_and_flags_numbers():
    by_ref = {m.ref: m for m in [
        msg(1, "实测一集 12 个镜头花了 360 积分", urls=[]),
        msg(2, "工作流放这里了 https://github.com/comfyanonymous/ComfyUI", urls=["https://github.com/comfyanonymous/ComfyUI"]),
    ]}
    it = item("一集 12 个镜头的成本", hook="花了 360 积分，约 99 元", refs={"m1", "m2"},
              evidence=[{"msg": "m2", "quote": "实测一集 12 个镜头花了 360 积分"},         # 编号错了，应改挂到 m1
                        {"msg": "m1", "quote": "这句话原文里没有"}],
              links=[{"url": "https://github.com/comfyanonymous/ComfyUI", "title": ""},
                     {"url": "https://evil.example.com/x", "title": ""}])
    stats = verify_item(it, by_ref)
    assert stats["valid"] == 1 and stats["relinked"] == 1 and stats["links_removed"] == 1
    assert it.evidence[0]["message_id"] == "1" and it.evidence[0]["sender"] == by_ref["m1"].sender
    assert [x["url"] for x in it.links] == ["https://github.com/comfyanonymous/ComfyUI"]
    assert it.unverified == ["99"] and "未核实" in it.risk_flags


def test_verify_item_without_valid_evidence_is_empty():
    by_ref = {"m1": msg(1, "原文内容在这里")}
    it = item("编造的情报", refs={"m1"}, evidence=[{"msg": "m1", "quote": "完全不同的一句话"}])
    verify_item(it, by_ref)
    assert it.evidence == []
