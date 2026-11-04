"""bureau.integrations.onebot：segments_to_text、verify_onebot_request、parse_onebot_event、客户端错误。"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from bureau.contracts import MessageKind, Platform
from bureau.integrations.onebot import (OneBotClient, OneBotError, onebot_credentials, parse_cq_string,
                                        parse_onebot_event, segments_to_text, verify_onebot_request)

from .helpers import MockHTTP, ok_json, refuse, run, ts

NEWS_CARD = json.dumps({"app": "com.tencent.structmsg", "prompt": "[分享]Claude Code 新功能",
                        "meta": {"news": {"title": "Claude Code 新功能", "desc": "一篇文章",
                                          "jumpUrl": "https://example.com/a?x=1"}}}, ensure_ascii=False)
MINIAPP = json.dumps({"app": "com.tencent.miniapp_01", "prompt": "[QQ小程序]哔哩哔哩",
                      "meta": {"detail_1": {"title": "哔哩哔哩", "desc": "某视频", "qqdocurl": "https://b23.tv/xyz"}}},
                     ensure_ascii=False)


def test_text_at_face_and_mentions():
    text, kind, atts, mentions, reply = segments_to_text([
        {"type": "text", "data": {"text": "大家看 "}},
        {"type": "at", "data": {"qq": "10001", "name": "张三"}},
        {"type": "at", "data": {"qq": "all"}},
        {"type": "face", "data": {"id": "14", "raw": {"faceText": "/微笑"}}},
    ])
    assert text == "大家看 @张三 @全体成员 [微笑]"
    assert kind is MessageKind.TEXT
    assert mentions == ["10001", "all"] and reply is None and atts == []


def test_reply_image_and_json_card():
    text, kind, atts, _, reply = segments_to_text([
        {"type": "reply", "data": {"id": "998877"}},
        {"type": "text", "data": {"text": "这个好用"}},
        {"type": "image", "data": {"file": "a.jpg", "url": "https://gchat.qpic.cn/x.jpg", "summary": ""}},
    ])
    assert kind is MessageKind.REPLY and reply == "998877"
    assert "这个好用" in text and "[图片]" in text
    assert atts[0].kind == "image" and atts[0].url == "https://gchat.qpic.cn/x.jpg"

    text, kind, atts, _, _ = segments_to_text([{"type": "json", "data": {"data": NEWS_CARD}}])
    assert kind is MessageKind.LINK
    assert text == "[链接] Claude Code 新功能 https://example.com/a?x=1"
    assert atts[0].kind == "link" and atts[0].title == "Claude Code 新功能"

    text, kind, atts, _, _ = segments_to_text([{"type": "json", "data": {"data": MINIAPP}}])
    assert kind is MessageKind.CARD and "哔哩哔哩" in text and atts[0].url == "https://b23.tv/xyz"


def test_forward_file_video_record_markdown_sticker():
    fwd = {"type": "forward", "data": {"id": "f1", "content": [
        {"sender": {"nickname": "甲"}, "message": [{"type": "text", "data": {"text": "第一条"}}]},
        {"sender": {"card": "乙"}, "message": [{"type": "text", "data": {"text": "第二条"}}]}]}}
    text, kind, *_ = segments_to_text([fwd])
    assert kind is MessageKind.FORWARD and text == "[合并转发] 共 2 条：甲：第一条；乙：第二条"

    text, kind, atts, *_ = segments_to_text([{"type": "file", "data": {"file": "报告.pdf", "file_id": "x"}}])
    assert kind is MessageKind.FILE and text == "[文件] 报告.pdf" and atts[0].title == "报告.pdf"
    assert segments_to_text([{"type": "video", "data": {"file": "v"}}])[1] is MessageKind.VIDEO
    assert segments_to_text([{"type": "record", "data": {"file": "r"}}])[:2] == ("[语音]", MessageKind.VOICE)
    assert segments_to_text([{"type": "markdown", "data": {"content": "**加粗**"}}])[:2] == ("**加粗**", MessageKind.TEXT)
    sticker = segments_to_text([{"type": "image", "data": {"file": "s.gif", "summary": "[动画表情]", "sub_type": 1}}])
    assert sticker[:2] == ("[表情]", MessageKind.STICKER)
    mface = segments_to_text([{"type": "image", "data": {"file": "m.gif", "summary": "[开心]", "emoji_id": "1"}}])
    assert mface[:2] == ("[开心]", MessageKind.STICKER)


def test_cq_string_is_supported():
    assert parse_cq_string("hi[CQ:at,qq=123]&#91;x&#93;")[1] == {"type": "at", "data": {"qq": "123"}}
    text, kind, _, mentions, reply = segments_to_text("[CQ:reply,id=5]收到[CQ:at,qq=42]")
    assert reply == "5" and mentions == ["42"] and kind is MessageKind.REPLY and text.startswith("收到")


BODY = json.dumps({"post_type": "message", "message_type": "group"}).encode()


def _sig(key: str, body: bytes = BODY) -> str:
    return "sha1=" + hmac.new(key.encode(), body, hashlib.sha1).hexdigest()


def test_verify_correct_signature():
    assert verify_onebot_request({"X-Signature": _sig("s3cret")}, BODY, secret="s3cret", token=None)
    # 头名大小写不敏感；NapCat 把 token 当签名密钥，只配置 token 时也能通过
    assert verify_onebot_request({"x-signature": _sig("tok")}, BODY, secret=None, token="tok")


def test_verify_wrong_signature():
    assert not verify_onebot_request({"X-Signature": _sig("other")}, BODY, secret="s3cret", token=None)
    assert not verify_onebot_request({"X-Signature": _sig("s3cret", b"tampered")}, BODY, secret="s3cret", token=None)
    assert not verify_onebot_request({"X-Signature": "md5=abc"}, BODY, secret="s3cret", token=None)
    assert not verify_onebot_request({}, BODY, secret="s3cret", token=None)


def test_verify_bearer_token():
    assert verify_onebot_request({"Authorization": "Bearer tok"}, BODY, secret=None, token="tok")
    assert verify_onebot_request({"authorization": "Token tok"}, BODY, secret="s", token="tok")
    assert not verify_onebot_request({"Authorization": "Bearer nope"}, BODY, secret=None, token="tok")


def test_verify_unconfigured_allows():
    assert verify_onebot_request({}, BODY, secret=None, token=None)
    assert verify_onebot_request({}, BODY, secret="", token="  ")


def test_credentials_helper():
    assert onebot_credentials({"token": "t"}) == (None, "t")
    assert onebot_credentials({"token": "t", "report_secret": "s"}) == ("s", "t")


GROUP_EVENT = {
    "time": ts("2026-10-25 18:14"), "self_id": 2000, "post_type": "message", "message_type": "group",
    "sub_type": "normal", "message_id": 123456, "message_seq": 123456, "real_seq": "88", "group_id": 765,
    "group_name": "AI 创作群", "user_id": 10001, "sender": {"user_id": 10001, "nickname": "张三昵称", "card": "张三"},
    "message": [{"type": "reply", "data": {"id": "111"}}, {"type": "text", "data": {"text": "收到，明天试试"}}],
    "raw_message": "[CQ:reply,id=111]收到，明天试试", "message_format": "array",
}


def test_parse_group_event():
    m = parse_onebot_event(GROUP_EVENT)
    assert m is not None and m.platform is Platform.QQ
    assert (m.group_native_id, m.group_name, m.native_id) == ("765", "AI 创作群", "123456")
    assert m.sender_name == "张三" and m.sender_id == "10001" and not m.is_self
    assert m.kind is MessageKind.REPLY and m.reply_to == "111" and m.text == "收到，明天试试"
    assert m.sent_at.isoformat() == "2026-10-25T18:14:00+08:00"


def test_parse_ignores_non_group_and_handles_self():
    assert parse_onebot_event({**GROUP_EVENT, "message_type": "private"}) is None
    assert parse_onebot_event({"post_type": "notice", "notice_type": "group_increase"}) is None
    assert parse_onebot_event({"post_type": "meta_event", "meta_event_type": "heartbeat"}) is None
    assert parse_onebot_event({**GROUP_EVENT, "time": "bad"}) is None
    mine = parse_onebot_event({**GROUP_EVENT, "post_type": "message_sent", "user_id": 2000,
                               "sender": {"user_id": 2000, "nickname": "小号"}})
    assert mine is not None and mine.is_self and mine.sender_name == "小号"
    string_fmt = parse_onebot_event({**GROUP_EVENT, "message": "[CQ:at,qq=1]你好", "message_format": "string"})
    assert string_fmt.mentions == ["1"] and "你好" in string_fmt.text


def test_client_errors_are_chinese():
    with pytest.raises(OneBotError) as e:
        run(OneBotClient("http://127.0.0.1:3010", transport=httpx.MockTransport(refuse)).call("get_login_info"))
    assert "连不上" in e.value.message and "6099" in (e.value.hint or "")
    http = MockHTTP(lambda r: httpx.Response(403, text='{"message":"token verify failed!"}'))
    with pytest.raises(OneBotError) as e:
        run(OneBotClient(token="x", transport=http.transport).call("get_login_info"))
    assert "token 不正确" in e.value.message
    assert http.requests[0].headers["Authorization"] == "Bearer x"
    http = MockHTTP(lambda r: ok_json({"status": "failed", "retcode": 1400, "data": None, "message": "参数错误：group_id"}))
    with pytest.raises(OneBotError) as e:
        run(OneBotClient(transport=http.transport).call("get_group_list"))
    assert "请求参数错误" in e.value.message and e.value.retcode == 1400