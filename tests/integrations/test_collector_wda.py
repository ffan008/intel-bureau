"""wechat.wda：health、列群、order=desc 分页回溯、消息映射（假 WDA 本地 API）。"""

from __future__ import annotations

import httpx
import pytest

from bureau.collectors import wechat_wda as wda_mod
from bureau.collectors.wechat_wda import SECURITY_NOTE, WdaCollector
from bureau.contracts import GroupInfo, Health, MessageKind, Platform

from .helpers import MockHTTP, collector_ctx, dt, ok_json, refuse, run, ts

ACCOUNTS_OK = {"status": "success", "accounts": ["wxid_me"], "default_account": "wxid_me",
               "default_switchable_account": "wxid_me",
               "accountInfos": [{"account": "wxid_me", "realtimeAvailable": True, "hasDecryptedDbs": True}]}
GROUP = GroupInfo(platform=Platform.WECHAT, native_id="1234@chatroom", name="AI 创作群")


def msg(i: int, when: str, rt: str = "text", **kw):
    base = {"id": f"message_0:Msg_x:{i}", "localId": i, "serverId": 9000 + i, "serverIdStr": str(9000 + i),
            "type": 1, "createTime": ts(when), "renderType": rt, "senderUsername": f"wxid_{i}",
            "senderDisplayName": f"群昵称{i}", "isSent": False, "content": f"消息{i}"}
    base.update(kw)
    return base


PAGES = [
    [msg(10, "2026-10-28 08:00"), msg(9, "2026-10-28 07:59", "link", title="Claude Code 教程",
                                         content="一篇好文章", url="https://mp.weixin.qq.com/s/abc", linkType="mp")],
    [msg(8, "2026-10-28 07:30", "quote", content="同意", quoteServerId="9007", quoteTitle="群昵称7", quoteContent="原话"),
     msg(7, "2026-10-28 07:00", "image", content="[图片]", imageUrl="http://127.0.0.1:10392/api/chat/media/image?x")],
    [msg(6, "2026-10-27 09:00", "file", content="[文件] 方案.pdf", title="方案.pdf", fileSize="1024"),
     msg(5, "2026-10-27 08:30", "system", content="张三 撤回了一条消息", serverId=0, serverIdStr=""),
     msg(4, "2026-10-27 06:00")],
]


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/chat/accounts":
        return ok_json(ACCOUNTS_OK)
    if path == "/api/chat/sessions":
        return ok_json({"status": "success", "sessions": [
            {"id": "1234@chatroom", "username": "1234@chatroom", "name": "AI 创作群", "isGroup": True,
             "avatar": "http://127.0.0.1:10392/api/chat/avatar?u=1"},
            {"id": "wxid_friend", "username": "wxid_friend", "name": "朋友", "isGroup": False}]})
    if path == "/api/chat/messages":
        assert request.url.params["order"] == "desc" and request.url.params["account"] == "wxid_me"
        page = int(request.url.params["offset"]) // 2
        return ok_json({"status": "success", "hasMore": page < 2, "messages": PAGES[page] if page < 3 else []})
    if path == "/api/chat/realtime/sync":
        return ok_json({"status": "success"})
    return httpx.Response(404, json={"detail": "Not Found"})


def make(tmp_path, h=handler, **settings):
    http = MockHTTP(h)
    return WdaCollector(collector_ctx(tmp_path, "wechat", settings), transport=http.transport), http


def test_health_ok_and_security_note(tmp_path):
    c, _ = make(tmp_path)
    h = run(c.health())
    assert h.ok and h.state is Health.OK and "wxid_me" in h.detail and SECURITY_NOTE in h.hint


def test_health_down_when_not_running(tmp_path):
    c, _ = make(tmp_path, refuse)
    h = run(c.health())
    assert not h.ok and h.state is Health.DOWN and "连不上" in h.detail
    assert "10392" in h.hint and SECURITY_NOTE in h.hint


def test_health_degraded_without_accounts(tmp_path):
    c, _ = make(tmp_path, lambda r: ok_json({"status": "error", "accounts": [],
                                            "message": "No chat accounts found. Please decrypt first."}))
    h = run(c.health())
    assert h.state is Health.DEGRADED and "解密" in h.detail


def test_list_groups_only_chatrooms(tmp_path):
    c, _ = make(tmp_path)
    groups = run(c.list_groups())
    assert [g.native_id for g in groups] == ["1234@chatroom"]
    assert groups[0].name == "AI 创作群" and groups[0].avatar_url is None   # 本机地址不外传


def test_fetch_pages_back_to_since_and_maps(tmp_path):
    c, http = make(tmp_path)
    res = run(c.fetch_messages(GROUP, dt("2026-10-27 08:00"), dt("2026-10-28 08:00")))
    offsets = [int(r.url.params["offset"]) for r in http.requests if r.url.path == "/api/chat/messages"]
    assert offsets == [0, 2, 4]                       # 回溯到早于 since 的那一页就停
    assert [m.native_id for m in res.messages] == [f"l5-{ts('2026-10-27 08:30')}", "9006", "9007", "9008", "9009"]
    assert res.complete
    by = {m.native_id: m for m in res.messages}
    assert by["9009"].kind is MessageKind.LINK and "https://mp.weixin.qq.com/s/abc" in by["9009"].text
    assert by["9009"].attachments[0].url == "https://mp.weixin.qq.com/s/abc"
    assert by["9008"].kind is MessageKind.REPLY and by["9008"].reply_to == "9007"
    assert by["9008"].quote_text == "群昵称7：原话"
    assert by["9007"].kind is MessageKind.IMAGE and by["9007"].attachments[0].url is None
    assert by["9006"].kind is MessageKind.FILE and by["9006"].attachments[0].title == "方案.pdf"
    assert by[f"l5-{ts('2026-10-27 08:30')}"].kind is MessageKind.RECALL
    assert all(m.sender_name.startswith("群昵称") for m in res.messages if m.kind is not MessageKind.RECALL)
    assert res.messages == sorted(res.messages, key=lambda m: m.sent_at)
    assert all(m.sent_at.utcoffset().total_seconds() == 8 * 3600 for m in res.messages)


def test_fetch_limit_keeps_latest(tmp_path):
    c, _ = make(tmp_path)
    res = run(c.fetch_messages(GROUP, dt("2026-10-27 08:00"), dt("2026-10-28 08:00"), limit=2))
    assert not res.complete and [m.native_id for m in res.messages] == ["9008", "9009"]


def test_sync_before_fetch_failure_is_warning(tmp_path):
    def h(request):
        if request.url.path == "/api/chat/realtime/sync":
            return httpx.Response(400, json={"detail": "WCDB realtime not available"})
        return handler(request)
    c, http = make(tmp_path, h, sync_before_fetch=True, source="decrypted")
    res = run(c.fetch_messages(GROUP, dt("2026-10-28 07:00"), dt("2026-10-28 08:00")))
    assert any(r.url.path == "/api/chat/realtime/sync" and r.method == "POST" for r in http.requests)
    assert res.warnings and "同步失败" in res.warnings[0]
    assert all(r.url.params.get("source") == "decrypted" for r in http.requests if r.url.path == "/api/chat/messages")


def test_fetch_error_is_readable(tmp_path):
    c, _ = make(tmp_path, refuse, account="wxid_me")
    try:
        run(c.fetch_messages(GROUP, dt("2026-10-27 08:00"), dt("2026-10-28 08:00")))
    except RuntimeError as exc:
        assert "WeChatDataAnalysis" in str(exc)
    else:
        raise AssertionError("应抛出中文异常")

# ---------------------------------------------------------------- 2.x 桌面版的 API Token
#
# 高级版 / 2.x 桌面版给本地 API 加了 Token 鉴权，不带就 401 external_token_required。

@pytest.fixture(autouse=True)
def _no_local_token(monkeypatch):
    """默认屏蔽开发机上真实存在的 Token，避免测试依赖本机是否装了 WDA。"""
    monkeypatch.setattr(wda_mod, "resolve_token", lambda root=None: "")


def _auth_probe():
    seen: dict[str, str | None] = {}

    def h(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat/accounts":
            seen["auth"] = request.headers.get("authorization")
            return ok_json(ACCOUNTS_OK)
        return httpx.Response(404, json={"detail": "Not Found"})

    return seen, h


def test_token_from_settings_is_sent(tmp_path):
    seen, h = _auth_probe()
    c = WdaCollector(collector_ctx(tmp_path, "wechat", {}, {"token": "tok-123"}), transport=MockHTTP(h).transport)
    run(c.health())
    assert seen["auth"] == "Bearer tok-123"


def test_autodiscovered_token_used_for_loopback(tmp_path, monkeypatch):
    monkeypatch.setattr(wda_mod, "resolve_token", lambda root=None: "auto-tok")
    seen, h = _auth_probe()
    c = WdaCollector(collector_ctx(tmp_path, "wechat"), transport=MockHTTP(h).transport)
    run(c.health())
    assert seen["auth"] == "Bearer auto-tok"


def test_autodiscovered_token_not_sent_to_remote_host(tmp_path, monkeypatch):
    """自动读到的本机 Token 不能发到别的机器上去（地址不是本机时不带鉴权头）。"""
    monkeypatch.setattr(wda_mod, "resolve_token", lambda root=None: "auto-tok")
    seen, h = _auth_probe()
    c = WdaCollector(collector_ctx(tmp_path, "wechat", {"base_url": "http://10.1.2.3:10392"}),
                     transport=MockHTTP(h).transport)
    run(c.health())
    assert seen["auth"] is None


def test_explicit_token_sent_even_to_remote_host(tmp_path):
    seen, h = _auth_probe()
    c = WdaCollector(collector_ctx(tmp_path, "wechat", {"base_url": "http://10.1.2.3:10392"}, {"token": "tok-9"}),
                     transport=MockHTTP(h).transport)
    run(c.health())
    assert seen["auth"] == "Bearer tok-9"


def test_401_token_required_gives_actionable_hint(tmp_path):
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"code": "external_token_required",
                                                    "message": "外部调用需要有效的应用访问凭据。"}})

    c = WdaCollector(collector_ctx(tmp_path, "wechat"), transport=MockHTTP(h).transport)
    status = run(c.health())
    assert status.state is Health.DOWN
    assert "Token" in status.detail
    assert "接口与 MCP" in status.hint                    # 指明去哪儿拿 Token


def test_401_with_saved_token_says_it_is_invalid(tmp_path):
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"code": "external_token_required",
                                                    "message": "外部调用需要有效的应用访问凭据。"}})

    c = WdaCollector(collector_ctx(tmp_path, "wechat", {}, {"token": "stale"}),
                     transport=MockHTTP(h).transport)
    status = run(c.health())
    assert "无效或已更换" in status.hint


ACCOUNTS_DIRECT = {"status": "success", "accounts": ["testaccount_2b85"],
                   "default_switchable_account": "testaccount_2b85",
                   "accountInfos": [{"account": "testaccount_2b85", "mode": "direct", "defaultSource": "realtime",
                                     "realtimeAvailable": False, "hasDecryptedDbs": False,
                                     "dataSourceStatus": {"activeSource": "realtime"}}]}


def test_health_direct_mode_counts_as_available(tmp_path):
    """桌面版「直连」不落解密快照，两个可用标志都是 false，但实时读取实际可用，不能报降级。"""
    http = MockHTTP(lambda r: ok_json(ACCOUNTS_DIRECT))
    c = WdaCollector(collector_ctx(tmp_path, "wechat"), transport=http.transport)
    status = run(c.health())
    assert status.state is Health.OK
    assert "实时读取可用" in status.detail


def test_health_missing_realtime_still_degraded(tmp_path):
    """既没直连也没解密库时仍然要提示降级，别把真的不可用当成可用。"""
    data = {"status": "success", "accounts": ["a"], "default_switchable_account": "a",
            "accountInfos": [{"account": "a", "mode": "snapshot", "realtimeAvailable": False,
                              "hasDecryptedDbs": False, "dataSourceStatus": {"activeSource": "decrypted"}}]}
    http = MockHTTP(lambda r: ok_json(data))
    c = WdaCollector(collector_ctx(tmp_path, "wechat"), transport=http.transport)
    status = run(c.health())
    assert status.state is Health.DEGRADED
