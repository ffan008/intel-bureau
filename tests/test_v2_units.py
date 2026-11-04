"""v2 单元测试：风险策略三种模式、提示词原文截取、链接分类与提取码、话题合并、知识库合并与版本、迁移兼容。"""

from __future__ import annotations

from types import SimpleNamespace

from bureau.core.constants import RISK_ILLEGAL
from bureau.core.textutil import share_code
from bureau.pipeline.links import classify_local, default_title
from bureau.pipeline.risk import blocks_feature, dropped_by_policy, penalty_of, policy_of
from bureau.pipeline.score import dimension_scores, select_v2, total_score
from bureau.pipeline.verify import slice_original
from tests.factories import item

W = {"novelty": 1.0, "actionability": 1.2, "credibility": 1.0, "heat": 0.9, "relevance": 1.1}


def _rc(policy: str | None, penalty: float | None = None):
    pipe = {} if policy is None else {"risk_policy": policy}
    if penalty is not None:
        pipe["risk_penalty"] = penalty
    settings = {"pipeline": pipe}
    return SimpleNamespace(cfg=lambda k, d=None: settings.get("pipeline", {}).get(k.split(".")[-1], d)
                           if k.startswith("pipeline.") else d)


def _items():
    out = []
    for i, (score, flags) in enumerate([(90, ["广告引流"]), (85, [RISK_ILLEGAL, "合规风险"]), (80, []), (70, ["金钱风险"]),
                                        (60, []), (50, []), (40, []), (30, []), (20, []), (10, [])]):
        it = item(f"话题{i}", steps=["第一步", "第二步"], evidence=[{"msg": "m1"}] * 2)
        it.score, it.risk_flags, it.trend, it.id = score, list(flags), "new", f"i{i}"
        out.append(it)
    return out


def test_risk_policy_label_flag_drop():
    assert policy_of(_rc(None)) == "label" and policy_of(_rc("bogus")) == "label"      # 新默认
    assert penalty_of(_rc("label", 0.6), "label") == 0.0                                # label 下配置了也不扣
    assert penalty_of(_rc("flag", 0.6), "flag") == 0.6
    mid = {k: 2.5 for k in W}
    assert total_score(mid, W, ["合规风险"], "new", penalty_of(_rc("label", 0.6), "label"), 1.2) == 50.0
    assert total_score(mid, W, ["合规风险"], "new", penalty_of(_rc("flag", 0.6), "flag"), 1.2) == 38.0
    ad = item("广告", risk_flags=["广告引流"])
    assert not blocks_feature(ad, "label") and blocks_feature(ad, "flag")
    assert dropped_by_policy(ad, "drop") and not dropped_by_policy(ad, "label")
    illegal = item("违法", risk_flags=[RISK_ILLEGAL])
    assert all(blocks_feature(illegal, p) for p in ("label", "flag", "drop"))           # 永远不进专题


def test_select_v2_label_keeps_risky_in_headlines_and_features():
    its = _items()
    select_v2(its, top_n=5, max_features=8, policy="label")
    by = {it.title: it for it in its}
    assert by["话题0"].is_headline and by["话题0"].is_feature                            # 广告引流也能进头条和专题
    assert not by["话题1"].is_headline and not by["话题1"].is_feature                    # 违法高危不能
    feats = sorted((it for it in its if it.is_feature), key=lambda x: x.seq)
    assert [it.seq for it in feats] == list(range(1, len(feats) + 1)) and len(feats) == 8
    its = _items()
    select_v2(its, top_n=5, max_features=8, policy="flag")                               # flag：v1 行为
    by = {it.title: it for it in its}
    assert not by["话题0"].is_headline and not by["话题3"].is_feature


def test_label_does_not_touch_credibility():
    rc = SimpleNamespace(cfg=lambda k, d=None: d)
    it = item("风险话题", risk_flags=["广告引流", "金钱风险", "未核实"])
    it.heat_raw = {"messages": 10, "participants": 4, "groups": 2, "depth": 2}
    clean = item("风险话题")
    clean.heat_raw = dict(it.heat_raw)
    assert dimension_scores(it, rc, 3.0, "label") == dimension_scores(clean, rc, 3.0, "label")
    assert dimension_scores(it, rc, 3.0, "flag")["credibility"] < dimension_scores(clean, rc, 3.0, "flag")["credibility"]


def test_slice_original_returns_database_text():
    raw = "MJ 版本：watercolor portrait,  loose washes --ar 3:4 --stylize 150\n【构图】主体居中"
    assert slice_original(raw, "watercolor portrait,  loose washes --ar 3:4") == "watercolor portrait,  loose washes --ar 3:4"
    # 模型漏抄了空白、把全角冒号写成半角：仍然返回数据库原文（不是模型的写法）
    assert slice_original(raw, "watercolor portrait, loose washes --ar 3:4 --stylize 150 【构图】主体居中") == \
        "watercolor portrait,  loose washes --ar 3:4 --stylize 150\n【构图】主体居中"
    assert slice_original("提示词：【风格】水彩，留白", "提示词:【风格】水彩，留白") == "提示词：【风格】水彩，留白"
    assert slice_original(raw, "完全不存在的一段提示词内容") is None                       # 编造的丢弃


def test_link_classify_title_and_share_code():
    cases = {"https://github.com/city96/ComfyUI-GGUF": "github", "https://x.com/a/status/1": "x",
             "https://twitter.com/a": "x", "https://mp.weixin.qq.com/s/abc": "wechat_article",
             "https://pan.baidu.com/s/1abc?pwd=a7k2": "netdisk", "https://pan.quark.cn/s/abc": "netdisk",
             "https://www.bilibili.com/video/BV1": "video", "https://docs.qq.com/doc/x": "doc",
             "https://example.com/a.pdf": "doc", "https://n8n.io/workflows/": "web", "ftp://x": "other"}
    for url, kind in cases.items():
        assert classify_local(url) == kind, url
    assert default_title("https://github.com/city96/ComfyUI-GGUF", "github") == "city96/ComfyUI-GGUF"
    assert default_title("https://pan.baidu.com/s/1abc", "netdisk") == "百度网盘 分享"
    text = "百度网盘 https://pan.baidu.com/s/1Abc?pwd=a7k2 提取码：a7k2，夸克 https://pan.quark.cn/s/xyz 不用提取码"
    assert share_code(text, "https://pan.baidu.com/s/1Abc?pwd=a7k2") == "a7k2"
    assert share_code(text, "https://pan.quark.cn/s/xyz") is None
    assert share_code("链接 https://pan.baidu.com/s/1Q 提取码 9xYz 别外传", "https://pan.baidu.com/s/1Q") == "9xYz"
    assert share_code("Claude Code 太好用了 https://pan.baidu.com/s/1Q", "https://pan.baidu.com/s/1Q") is None
