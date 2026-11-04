"""qq.onebot：health、列群、按 message_seq 向前翻页、消息映射（假 NapCat）。"""

from __future__ import annotations

import json

import httpx

from bureau.collectors.qq_onebot import OneBotCollector
from bureau.contracts import GroupInfo, Health, MessageKind, Platform

from .helpers import MockHTTP, collector_ctx, dt, ok_json, refuse, run, ts

GROUP = GroupInfo(platform=Platform.QQ, native_id="765", name="AI 创作群")


def m(mid: int, when: str, text: str, **kw):
    base = {"time": ts(when), "message_id": mid, "message_seq": mid, "real_seq": str(mid), "group_id": 765,
            "user_id": 10000 + mid, "sender": {"user_id": 10000 + mid, "nickname": f"昵称{mid}", "card": f"群名片{mid}"},
            "message": [{"type": "text", "data": {"text": text}}], "message_type": "group", "post_type": "message"}
    base.update(kw)
    return base


# NapCat：不带 message_seq 取最新；带 message_seq 时返回更早的消息并包含这条锚点；按时间从旧到新
HISTORY = {
    None: [m(5, "2026-10-28 07:00", "e"), m(6, "2026-10-28 07:30", "f",
            message=[{"type": "reply", "data": {"id": "4"}}, {"type": "text", "data": {"text": "回复 d"}}]),
           m(7, "2026-10-28 09:00", "窗口外")],
    "5": [m(3, "2026-10-28 06:00", "c"), m(4, "2026-10-28 06:30", "d"), m(5, "2026-10-28 07:00", "e")],
    "3": [m(1, "2026-10-27 05:00", "a"), m(2, "2026-10-27 09:00", "b"), m(3, "2026-10-28 06:00", "c")],
}


def handler(request: httpx.Request) -> httpx.Response:
    action = request.url.path.lstrip("/")
    body = json.loads(request.content or b"{}")
    if request.headers.get("Authorization") != "Bearer tk":
        return httpx.Response(403, text='{"message":"token verify failed!"}')
    if action == "get_login_info":
        return ok_json({"status": "ok", "retcode": 0, "data": {"user_id": 2000, "nickname": "情报员"}})
    if action == "get_group_list":
        return ok_json({"status": "ok", "retcode": 0, "data": [
            {"group_id": 765, "group_name": "AI 创作群", "member_count": 321, "max_member_count": 500}]})
    if action == "get_group_msg_history":
        assert isinstance(body["group_id"], str) and body["count"] == 50
        return ok_json({"status": "ok", "retcode": 0, "data": {"messages": HISTORY[body.get("message_seq")]}})
    return ok_json({"status": "failed", "retcode": 1404, "message": "不支持的Api"})


def make(tmp_path, h=handler, token="tk"):
    http = MockHTTP(h)
    return OneBotCollector(collector_ctx(tmp_path, "qq", {}, {"token": token}), transport=http.transport), http


def test_health(tmp_path):
    h = run(make(tmp_path)[0].health())
    assert h.ok and "情报员" in h.detail and h.data["self_id"] == "2000"
    bad = run(make(tmp_path, token="wrong")[0].health())
    assert not bad.ok and "token" in bad.detail
    down = run(make(tmp_path, refuse)[0].health())
    assert down.state is Health.DOWN and "NapCat" in down.detail and "6099" in down.hint


def test_list_groups(tmp_path):
    groups = run(make(tmp_path)[0].list_groups())
    assert groups[0].native_id == "765" and groups[0].member_count == 321


def test_fetch_pages_backwards_by_message_seq(tmp_path):
    c, http = make(tmp_path)
    res = run(c.fetch_messages(GROUP, dt("2026-10-27 08:00"), dt("2026-10-28 08:00")))
    seqs = [json.loads(r.content).get("message_seq") for r in http.requests]
    assert seqs == [None, "5", "3"]
    assert [x.native_id for x in res.messages] == ["2", "3", "4", "5", "6"]
    assert res.complete and res.messages[0].sender_name == "群名片2"
    reply = res.messages[-1]
    assert reply.kind is MessageKind.REPLY and reply.reply_to == "4" and reply.quote_text == "d"


def test_fetch_stops_when_anchor_missing(tmp_path):
    def h(request):
        body = json.loads(request.content or b"{}")
        if body.get("message_seq") == "5":
            return ok_json({"status": "failed", "retcode": 200, "message": "消息5不存在"})
        return handler(request)
    res = run(make(tmp_path, h)[0].fetch_messages(GROUP, dt("2026-10-27 08:00"), dt("2026-10-28 08:00")))
    assert [x.native_id for x in res.messages] == ["5", "6"] and res.warnings