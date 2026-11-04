"""wechat.weflow：health、列群、ChatLab Pull 按 sync 分页、/api/v1/messages 模式与映射（假 WeFlow）。"""

from __future__ import annotations

import httpx

from bureau.collectors.wechat_weflow import DECRYPT_NOTE, WeFlowCollector
from bureau.contracts import GroupInfo, Health, MessageKind, Platform

from .helpers import MockHTTP, collector_ctx, dt, ok_json, refuse, run, ts

GROUP = GroupInfo(platform=Platform.WECHAT, native_id="555@chatroom", name="项目群")
MEMBERS = [{"platformId": "wxid_a", "accountName": "张三", "groupNickname": "产品-张三"}]


def chatlab_page(msgs, sync):
    return {"chatlab": {"version": "0.0.2", "exportedAt": 1, "generator": "WeFlow"},
            "meta": {"name": "项目群", "platform": "im", "type": "group", "groupId": "555@chatroom"},
            "members": MEMBERS, "messages": msgs, "sync": sync}


def handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p == "/health":
        return ok_json({"status": "ok"})
    if request.headers.get("Authorization") != "Bearer good":
        return httpx.Response(401, json={"error": "Unauthorized"})
    if p == "/api/v1/sessions":
        return ok_json({"success": True, "count": 2, "sessions": [
            {"username": "555@chatroom", "displayName": "项目群", "type": 2, "lastTimestamp": 1},
            {"username": "wxid_b", "displayName": "李四", "type": 1}]})
    if p == "/api/v1/sessions/555%40chatroom/messages" or p == "/api/v1/sessions/555@chatroom/messages":
        off = int(request.url.params["offset"])
        if off == 0:
            return ok_json(chatlab_page([
                {"sender": "wxid_a", "accountName": "张三", "timestamp": ts("2026-10-28 07:00"), "type": 0,
                 "content": "早", "platformMessageId": "m1"},
                {"sender": "wxid_c", "accountName": "王五", "timestamp": ts("2026-10-28 07:10"), "type": 7,
                 "content": "[链接] 好文 https://example.com/p", "platformMessageId": "m2"}],
                {"hasMore": True, "nextSince": request.url.params["since"], "nextOffset": 2}))
        return ok_json(chatlab_page([
            {"sender": "wxid_a", "accountName": "张三", "timestamp": ts("2026-10-28 07:20"), "type": 25,
             "content": "同意", "platformMessageId": "m3", "replyToMessageId": "m2"},
            {"sender": "wxid_a", "accountName": "张三", "timestamp": ts("2026-10-28 09:00"), "type": 0,
             "content": "窗口外", "platformMessageId": "m4"}], {"hasMore": False}))
    if p == "/api/v1/group-members":
        return ok_json({"success": True, "members": [{"wxid": "wxid_a", "groupNickname": "产品-张三", "displayName": "张三"}]})
    if p == "/api/v1/messages":
        return ok_json({"success": True, "hasMore": False, "messages": [
            {"localId": 1, "serverId": "601", "localType": 1, "createTime": ts("2026-10-28 07:00"), "isSend": 0,
             "senderUsername": "wxid_a", "content": "你好", "parsedContent": "你好"},
            {"localId": 2, "serverId": "602", "localType": 244813135921, "createTime": ts("2026-10-28 07:05"),
             "isSend": 1, "senderUsername": "wxid_me", "content": "收到", "replyToMessageId": "601",
             "quote": {"platformMessageId": "601", "accountName": "张三", "content": "你好"}}]})
    return httpx.Response(404)


def make(tmp_path, token="good", h=handler, **settings):
    http = MockHTTP(h)
    ctx = collector_ctx(tmp_path, "wechat", settings, {"token": token} if token else {})
    return WeFlowCollector(ctx, transport=http.transport), http


def test_health_states(tmp_path):
    assert run(make(tmp_path)[0].health()).state is Health.OK
    h = run(make(tmp_path, token="bad")[0].health())
    assert h.state is Health.DEGRADED and "Token" in h.detail and DECRYPT_NOTE in h.hint
    assert run(make(tmp_path, token=None)[0].health()).state is Health.UNCONFIGURED
    down = run(make(tmp_path, h=refuse)[0].health())
    assert down.state is Health.DOWN and "5031" in down.hint and "解密组件" in down.hint


def test_list_groups(tmp_path):
    groups = run(make(tmp_path)[0].list_groups())
    assert [(g.native_id, g.name) for g in groups] == [("555@chatroom", "项目群")]


def test_chatlab_pull_pages_by_sync(tmp_path):
    c, http = make(tmp_path)
    res = run(c.fetch_messages(GROUP, dt("2026-10-28 06:00"), dt("2026-10-28 08:00")))
    pulls = [r for r in http.requests if r.url.path.endswith("/messages") and "sessions" in r.url.path]
    assert [int(r.url.params["offset"]) for r in pulls] == [0, 2]
    assert [m.native_id for m in res.messages] == ["m1", "m2", "m3"]
    assert res.messages[0].sender_name == "产品-张三"           # 群昵称优先
    assert res.messages[1].kind is MessageKind.LINK and res.messages[1].attachments[0].url == "https://example.com/p"
    assert res.messages[2].kind is MessageKind.REPLY and res.messages[2].reply_to == "m2"


def test_messages_mode_uses_group_member_names(tmp_path):
    c, _ = make(tmp_path, mode="messages")
    res = run(c.fetch_messages(GROUP, dt("2026-10-28 06:00"), dt("2026-10-28 08:00")))
    assert [m.native_id for m in res.messages] == ["601", "602"]
    assert res.messages[0].sender_name == "产品-张三"
    assert res.messages[1].kind is MessageKind.REPLY and res.messages[1].is_self
    assert res.messages[1].quote_text == "张三：你好"