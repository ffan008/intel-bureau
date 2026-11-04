"""清洗、统计与 z 值、切块、合并。"""

from __future__ import annotations

from collections import Counter

from bureau.core.textutil import desensitize
from bureau.pipeline.clean import clean_rows
from bureau.pipeline.merge import cluster
from bureau.pipeline.segment import build_threads, pack_chunks
from bureau.pipeline.stats import compute_stats
from tests.factories import T0, cand, msg, row

CFG = {"drop_kinds": ["system", "recall", "redpacket", "sticker"], "min_chars": 4, "dedupe_min_chars": 12,
       "low_info_patterns": [r"^(收到|好的?|\+1|6+|哈+)[!！。.~\s]*$", r"^\[(图片|表情)\]$", "拍了拍"], "desensitize": True}
PRIV = {"desensitize": ["phone", "email", "idcard", "bankcard", "wechat_id"]}


def test_clean_drops_noise_and_keeps_content():
    rows = [row(1, "收到"), row(2, "+1"), row(3, "[图片]", kind="image"), row(4, "哈哈哈"),
            row(5, '"阿杰" 拍了拍 "小鹿"', kind="system"), row(6, "恭喜发财", kind="redpacket"),
            row(7, "😂😂😂"), row(8, "ComfyUI 用 fp8 版本可以在 8G 显存跑 Flux"), row(9, "好的！"),
            row(10, "[链接] 风格词对照表", kind="link", attachments=[{"kind": "link", "url": "https://example.com/a"}])]
    out, info = clean_rows(rows, CFG, PRIV)
    assert [m.native_id for m in out] == ["n8", "n10"]
    assert out[1].urls == ["https://example.com/a"]
    assert info["raw"] == 10 and info["clean"] == 2 and info["snr"] == 0.2
    assert sum(info["drops"].values()) == 8


def test_clean_cross_group_dedupe_records_spread():
    text = "Claude Code 的 Skill 要写清楚 description，触发才准"
    rows = [row(1, text, group="wechat:a"), row(2, text, group="qq:b"), row(3, text + "！", group="feishu:c")]
    out, info = clean_rows(rows, CFG, PRIV)
    assert len(out) == 1
    assert sorted(out[0].spread_groups) == ["feishu:c", "qq:b"]
    assert info["drops"]["dup_cross"] == 2


def test_clean_desensitize_and_reply_refs():
    rows = [row(1, "有事打我电话 13812345678 或发邮件 a.b@example.com"),
            row(2, "收藏这个 https://example.com/p/13812345678 链接很有用", reply_to="n1")]
    out, info = clean_rows(rows, CFG, PRIV)
    assert "13812345678" not in out[0].text and "[手机号]" in out[0].text and "[邮箱]" in out[0].text
    assert "https://example.com/p/13812345678" in out[1].text          # URL 内部不脱敏
    assert out[1].reply_ref == out[0].ref == "m1"
    assert info["masked"] == 2
    assert desensitize("加我微信：abc_12345 领资料", ["wechat_id"])[0] == "加我微信：[微信号] 领资料"
    assert desensitize("Review the code", ["wechat_id"])[1] == 0


def test_stats_z_value_rising_and_new():
    texts = ["首尾帧模式做漫剧转场很顺"] * 6 + ["漫剧这周特别火，大家都在做"] * 9 + ["今天出图效果不错，水彩风很稳"] * 3
    rows = [row(i, t + f" #{i}") for i, t in enumerate(texts, start=1)]
    clean, _ = clean_rows(rows, CFG, PRIV)
    baseline = [Counter({"漫剧": 1, "出图": 3}) for _ in range(6)] + [None]
    st, internal = compute_stats(rows, clean, end=T0.replace(hour=23), tz="Asia/Shanghai", week_ts=[], baseline=baseline)
    rising = {r["word"]: r for r in st["rising"]}
    assert "首尾帧" in rising and rising["首尾帧"]["avg7"] == 0 and rising["首尾帧"]["today"] == 6
    assert rising["漫剧"]["today"] == 15 and rising["漫剧"]["avg7"] == 1.0 and rising["漫剧"]["z"] == 14.0
    assert "出图" not in rising                                         # 与基线持平
    trends = {k["word"]: k["trend"] for k in st["keywords"]}
    assert trends["首尾帧"] == "new" and trends["漫剧"] == "up" and trends["出图"] == "flat"
    assert len(rising["漫剧"]["spark"]) == 7 and rising["漫剧"]["spark"][-1] == 15
    assert len(st["hourly"]) == 24 and len(st["heat_7x24"]) == 168
    assert st["messages_raw"] == st["messages_clean"] == 18


def test_stats_needs_three_baseline_days():
    rows = [row(i, f"首尾帧漫剧教程第 {i} 集") for i in range(1, 9)]
    clean, _ = clean_rows(rows, CFG, PRIV)
    st, _ = compute_stats(rows, clean, end=T0.replace(hour=23), tz="Asia/Shanghai", week_ts=[],
                          baseline=[None] * 5 + [Counter(), Counter()])
    assert st["rising"] == []


def test_segment_threads_and_chunks():
    msgs = [msg(1, "第一段讨论开始"), msg(2, "继续第一段", minutes=5), msg(3, "第二段讨论（隔了很久）", minutes=60),
            msg(4, "回复第一段的内容", minutes=62, reply_ref="m1")]
    threads = build_threads(msgs, gap_minutes=20)
    assert len(threads) == 2
    assert [m.ref for m in threads[0].msgs] == ["m1", "m2", "m4"]       # 回复链挂回原线程
    many = [msg(i, f"这是第 {i} 条比较长的消息内容，用来测试切块预算" * 3, minutes=i) for i in range(1, 60)]
    chunks = pack_chunks(build_threads(many, 20), "Asia/Shanghai", budget=1500)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1500 for c in chunks)
    assert sum(len(c.msgs) for c in chunks) == 59
    assert "[m1]" in chunks[0].text and chunks[0].hash and chunks[0].group_key == "qq:g1"


def test_merge_clusters_similar_and_shared_links():
    cs = [cand("即梦首尾帧做漫剧的流程", tags=["即梦", "首尾帧", "漫剧"]),
          cand("用即梦首尾帧做漫剧流程分享", tags=["即梦", "首尾帧", "漫剧"], group="wechat:x"),
          cand("n8n 自托管跑定时任务", tags=["n8n", "自动化"], links=["https://n8n.io/workflows/"]),
          cand("Dify 和 n8n 怎么选", tags=["Dify"], links=["https://n8n.io/workflows"]),
          cand("公众号流量主收益复盘", tags=["公众号", "流量主"])]
    groups, _ = cluster(cs, 0.35)
    sets = sorted(sorted(g) for g in groups)
    assert sets == [[0, 1], [2, 3], [4]]


def test_collect_platform_sums_inserted_across_concurrent_groups(monkeypatch):
    """并发采集时「新入库」要按群累加：out["inserted"] += await ... 会让结果互相覆盖。"""
    import asyncio
    from bureau.pipeline import collect

    async def fake_fetch(rc, collector, g, sem):
        await asyncio.sleep(g["delay"])
        return g["n"]

    class _Log:
        def info(self, *a, **k):
            pass

        def warn(self, *a, **k):
            pass

    class _RC:
        failed_groups: list = []
        log = _Log()

        def cfg(self, key, default=None):
            return default

    class _Collector:
        async def aclose(self):
            pass

    monkeypatch.setattr(collect, "_fetch_group", fake_fetch)
    groups = [{"key": "a", "name": "群A", "n": 3, "delay": 0.03},
              {"key": "b", "name": "群B", "n": 5, "delay": 0.01},
              {"key": "c", "name": "群C", "n": 0, "delay": 0}]     # 0 条的那个群最后完成
    out = asyncio.run(collect._collect_platform(_RC(), "wechat", groups, _Collector()))
    assert out["inserted"] == 8
