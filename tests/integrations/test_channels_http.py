"""HTTP 推送通道：成功、业务失败、网络失败（重试）、分段、签名 / 鉴权、幂等（全部用 MockTransport）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx

from bureau.channels.feishu_webhook import FeishuWebhookChannel, gen_sign
from bureau.channels.pushplus import PushPlusChannel
from bureau.channels.serverchan import ServerChanChannel, serverchan_url
from bureau.channels.wecom_webhook import WecomWebhookChannel
from bureau.channels.wxpusher import WxPusherChannel

from .helpers import MockHTTP, channel_ctx, make_report, ok_json, refuse, run

FEISHU_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/abc-123"
LONG_MD = "\n".join(f"- 第 {i} 条：" + "很长的中文内容" * 20 for i in range(400))      # 约 170 KB


def make(cls, tmp_path, handler, settings=None, secrets=None):
    http = MockHTTP(handler)
    ch = cls(channel_ctx(tmp_path, settings, secrets))
    ch.transport, ch.retry_base_delay, ch.part_interval = http.transport, 0, 0
    return ch, http


# ---------------------------------------------------------------- 飞书 Webhook

def test_feishu_sign_matches_reference():
    expected = base64.b64encode(hmac.new(b"1599360473\nsecret", b"", hashlib.sha256).digest()).decode()
    assert gen_sign(1599360473, "secret") == expected


def test_feishu_success_card_and_signature(tmp_path):
    ch, http = make(FeishuWebhookChannel, tmp_path, lambda r: ok_json({"code": 0, "msg": "success", "data": {}}),
                    secrets={"webhook_url": FEISHU_URL, "sign_secret": "s3"})
    res = run(ch.send(make_report()))
    assert res.ok and res.parts == 1 and res.kind == "feishu_webhook"
    body = http.body()
    assert body["msg_type"] == "interactive" and body["card"]["schema"] == "2.0"
    assert body["card"]["header"]["title"]["content"].startswith("情报局")
    md = body["card"]["body"]["elements"][0]["content"]
    assert "今日风向" in md and "http://127.0.0.1:8765/#/reports/r-20261028" in md
    assert body["sign"] == gen_sign(int(body["timestamp"]), "s3")


def test_feishu_business_failure_not_retried(tmp_path):
    ch, http = make(FeishuWebhookChannel, tmp_path, lambda r: ok_json({"code": 19021, "msg": "sign match fail"}),
                    secrets={"webhook_url": FEISHU_URL})
    res = run(ch.send(make_report()))
    assert not res.ok and "签名校验失败" in res.detail and len(http.requests) == 1
    assert "abc-123" not in res.detail


def test_feishu_network_failure_retries_twice(tmp_path):
    ch, http = make(FeishuWebhookChannel, tmp_path, refuse, secrets={"webhook_url": FEISHU_URL})
    res = run(ch.send(make_report()))
    assert not res.ok and res.retryable and len(http.requests) == 3 and "无法连接飞书" in res.detail
    assert "abc-123" not in res.detail


def test_feishu_splits_long_report_and_is_idempotent(tmp_path):
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return ok_json({"code": 11232, "msg": "frequency"}) if calls["n"] == 2 else ok_json({"code": 0})
    ch, http = make(FeishuWebhookChannel, tmp_path, flaky, secrets={"webhook_url": FEISHU_URL})
    report = make_report(summary_md=LONG_MD)
    res = run(ch.send(report))
    assert res.ok and res.parts > 5
    assert all(len(r.content) <= 20 * 1024 for r in http.requests)
    titles = [json.loads(r.content)["card"]["header"]["title"]["content"] for r in http.requests]
    assert titles[0].endswith(f"（1/{res.parts}）") and len(http.requests) == res.parts + 1   # 限流那次重试了
    sent = len(http.requests)
    again = run(ch.send(report))
    assert again.ok and "已投递过" in again.detail and len(http.requests) == sent       # 同一报告不重复发送


# ---------------------------------------------------------------- 企业微信

def test_wecom_success_and_byte_limit(tmp_path):
    ch, http = make(WecomWebhookChannel, tmp_path, lambda r: ok_json({"errcode": 0, "errmsg": "ok"}),
                    secrets={"webhook": "693a91f6-7xxx-4bc4"})
    res = run(ch.send(make_report(summary_md=LONG_MD)))
    assert res.ok and res.parts == len(http.requests) > 1
    assert str(http.requests[0].url).startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=693a91f6")
    for r in http.requests:
        body = json.loads(r.content)
        assert body["msgtype"] == "markdown_v2"
        assert len(body["markdown_v2"]["content"].encode("utf-8")) <= 4096
    assert json.loads(http.requests[1].content)["markdown_v2"]["content"].startswith(f"（2/{res.parts}）")


def test_wecom_business_failure_and_resume(tmp_path):
    state = {"n": 0}

    def h(request):
        state["n"] += 1
        return ok_json({"errcode": 93000, "errmsg": "invalid webhook url"}) if state["n"] == 2 else ok_json({"errcode": 0})
    ch, http = make(WecomWebhookChannel, tmp_path, h,
                    secrets={"webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k1"})
    report = make_report(summary_md=LONG_MD)
    first = run(ch.send(report))
    assert not first.ok and "第 2/" in first.detail and "Webhook 地址无效" in first.detail and first.parts == 1
    second = run(ch.send(report))                                   # 再投递时只补发剩余部分
    assert second.ok and "补发" in second.detail
    contents = [json.loads(r.content)["markdown_v2"]["content"][:6] for r in http.requests]
    assert contents.count(contents[0]) == 1                         # 第 1 段没有重复发


def test_wecom_rejects_foreign_host(tmp_path):
    ch, _ = make(WecomWebhookChannel, tmp_path, refuse, secrets={"webhook": "https://evil.example.com/?key=x"})
    res = run(ch.send(make_report()))
    assert not res.ok and "qyapi.weixin.qq.com" in res.detail


# ---------------------------------------------------------------- Server酱

def test_serverchan_urls():
    assert serverchan_url("SCT123abc") == "https://sctapi.ftqq.com/SCT123abc.send"
    assert serverchan_url("sctp42tABCDEF") == "https://42.push.ft07.com/send/sctp42tABCDEF.send"


def test_serverchan_sc3_success(tmp_path):
    ch, http = make(ServerChanChannel, tmp_path, lambda r: ok_json({"code": 0, "message": "", "data": {"pushid": "77"}}),
                    settings={"tags": "情报局"}, secrets={"sendkey": "sctp42tKEY"})
    res = run(ch.send(make_report(title="标题\n有换行" + "长" * 50)))
    assert res.ok and res.external_id == "77"
    body = http.body()
    assert http.requests[0].url.host == "42.push.ft07.com" and body["tags"] == "情报局"
    assert "\n" not in body["title"] and len(body["title"]) <= 32
    assert "- 一条判断\n\n- 另一条判断" in body["desp"]               # Server酱³ 需要两个换行


def test_serverchan_failures(tmp_path):
    ch, http = make(ServerChanChannel, tmp_path, lambda r: ok_json({"code": 40001, "message": "bad pushkey"}),
                    secrets={"sendkey": "SCTabc"})
    res = run(ch.send(make_report()))
    assert not res.ok and "bad pushkey" in res.detail and len(http.requests) == 1
    ch, http = make(ServerChanChannel, tmp_path, lambda r: httpx.Response(429, json={"code": 429}),
                    secrets={"sendkey": "SCTabc"})
    res = run(ch.send(make_report(report_id="r2")))
    assert not res.ok and "24 小时" in res.detail and len(http.requests) == 1   # 429 不重试
    ch, http = make(ServerChanChannel, tmp_path, refuse, secrets={"sendkey": "SCTsecretkey"})
    res = run(ch.send(make_report(report_id="r3")))
    assert not res.ok and len(http.requests) == 3 and "SCTsecretkey" not in res.detail
    assert ServerChanChannel(channel_ctx(tmp_path, {}, {"sendkey": "sctpXYZ"})).validate()


# ---------------------------------------------------------------- PushPlus

def test_pushplus_success_and_params(tmp_path):
    ch, http = make(PushPlusChannel, tmp_path, lambda r: ok_json({"code": 200, "msg": "请求成功", "data": "abc123"}),
                    settings={"topic": "t1", "channel": "wechat"}, secrets={"token": "tok"})
    res = run(ch.send(make_report()))
    assert res.ok and res.external_id == "abc123" and "异步" in res.detail
    body = http.body()
    assert str(http.requests[0].url) == "https://www.pushplus.plus/send"
    assert body["template"] == "markdown" and body["topic"] == "t1" and body["token"] == "tok"
    assert len(body["title"]) <= 100


def test_pushplus_failures_and_split(tmp_path):
    ch, http = make(PushPlusChannel, tmp_path, lambda r: ok_json({"code": 903, "msg": "无效的用户token"}),
                    secrets={"token": "tok"})
    res = run(ch.send(make_report()))
    assert not res.ok and "token 无效" in res.detail and len(http.requests) == 1
    ch, http = make(PushPlusChannel, tmp_path, lambda r: ok_json({"code": 500, "msg": "系统异常"}),
                    secrets={"token": "tok"})
    res = run(ch.send(make_report(report_id="r2")))
    assert not res.ok and res.retryable and len(http.requests) == 3
    ch, http = make(PushPlusChannel, tmp_path, lambda r: ok_json({"code": 200, "data": "x"}), secrets={"token": "tok"})
    res = run(ch.send(make_report(report_id="r3", summary_md=LONG_MD)))
    assert res.ok and res.parts == len(http.requests) > 1
    assert all(len(json.loads(r.content)["content"]) <= 18000 for r in http.requests)


# ---------------------------------------------------------------- WxPusher

def test_wxpusher_spt_and_standard(tmp_path):
    ok = lambda r: ok_json({"code": 1000, "msg": "处理成功", "success": True,
                            "data": [{"uid": "UID_a", "code": 1000, "status": "创建发送任务成功", "messageContentId": 9}]})
    ch, http = make(WxPusherChannel, tmp_path, ok, settings={"mode": "spt"}, secrets={"spt": "SPT_one"})
    res = run(ch.send(make_report()))
    assert res.ok and res.external_id == "9"
    body = http.body()
    assert str(http.requests[0].url).endswith("/api/send/message/simple-push")
    assert body["spt"] == "SPT_one" and body["contentType"] == 3 and len(body["summary"]) <= 100
    ch, http = make(WxPusherChannel, tmp_path, ok, settings={"mode": "standard", "uids": "UID_a, UID_b", "topic_ids": "12"},
                    secrets={"app_token": "AT_x"})
    assert run(ch.send(make_report(report_id="r-standard"))).ok      # 同一 report+channel 会被幂等账本跳过
    body = http.body()
    assert body["appToken"] == "AT_x" and body["uids"] == ["UID_a", "UID_b"] and body["topicIds"] == [12]


def test_wxpusher_failures_and_validation(tmp_path):
    ch, http = make(WxPusherChannel, tmp_path, lambda r: ok_json({"code": 1001, "msg": "内容过长"}),
                    secrets={"spt": "SPT_a,SPT_b"})
    res = run(ch.send(make_report()))
    assert not res.ok and "内容过长" in res.detail and http.body()["sptList"] == ["SPT_a", "SPT_b"]
    partial = lambda r: ok_json({"code": 1000, "data": [{"uid": "a", "code": 1000}, {"uid": "b", "code": 1001,
                                                                                     "status": "用户已取关"}]})
    ch, _ = make(WxPusherChannel, tmp_path, partial, settings={"mode": "standard", "uids": "a,b"},
                 secrets={"app_token": "AT"})
    res = run(ch.send(make_report(report_id="r2")))
    assert res.ok and "1 个目标未受理" in res.detail
    bad = WxPusherChannel(channel_ctx(tmp_path, {"mode": "standard"}, {}))
    assert {"缺少必填项：appToken", "标准推送需要至少一个 UID 或 Topic ID"} <= set(bad.validate())
    assert not run(bad.send(make_report())).ok


# ---------------------------------------------------------------- 各通道共有：网络失败与分段

NET_CASES = [
    (WecomWebhookChannel, {}, {"webhook": "k-123"}, "k-123"),
    (PushPlusChannel, {}, {"token": "pp-secret"}, "pp-secret"),
    (WxPusherChannel, {"mode": "spt"}, {"spt": "SPT_secret"}, "SPT_secret"),
]


def test_network_failure_retries_and_hides_secret(tmp_path):
    for cls, settings, secrets, secret in NET_CASES:
        ch, http = make(cls, tmp_path, refuse, settings=settings, secrets=secrets)
        res = run(ch.send(make_report(report_id=f"net-{cls.kind}")))
        assert not res.ok and res.retryable, cls.kind
        assert len(http.requests) == 3, cls.kind                      # 1 次 + 重试 2 次
        assert secret not in res.detail and "无法连接" in res.detail, cls.kind


def test_serverchan_and_wxpusher_split_long_reports(tmp_path):
    huge = "\n".join("段落" + "中文内容" * 300 for _ in range(40))       # 约 290 KB
    ch, http = make(ServerChanChannel, tmp_path, lambda r: ok_json({"code": 0, "data": {}}),
                    secrets={"sendkey": "SCTabc"})
    res = run(ch.send(make_report(summary_md=huge)))
    assert res.ok and res.parts == len(http.requests) > 1
    bodies = [json.loads(r.content) for r in http.requests]
    assert all(len(b["desp"].encode("utf-8")) <= 30000 for b in bodies)
    assert bodies[1]["title"].startswith(f"(2/{res.parts})") and all(len(b["title"]) <= 32 for b in bodies)
    ch, http = make(WxPusherChannel, tmp_path, lambda r: ok_json({"code": 1000, "data": []}),
                    secrets={"spt": "SPT_x"})
    res = run(ch.send(make_report(summary_md=huge)))
    assert res.ok and res.parts == len(http.requests) > 1
    bodies = [json.loads(r.content) for r in http.requests]
    assert all(len(b["content"].encode("utf-8")) <= 30000 for b in bodies)
    assert bodies[0]["summary"].endswith(f"（1/{res.parts}）")