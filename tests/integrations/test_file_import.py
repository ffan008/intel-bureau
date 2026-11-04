"""parse_export 的每种格式，以及 FileImportCollector（data/inbox + .processed.json）。"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from bureau.collectors.file_import import FileImportCollector, ImportFormatError, parse_export
from bureau.contracts import Health, MessageKind, Platform

from .helpers import collector_ctx, dt, run, ts

ARCH_SAMPLE = "🐯小象\n2026年10月25日 18:14\n以后每日风向标就发飞书了……\n"


def wda_doc(username="1234@chatroom", name="AI 创作群", msgs=None):
    return {"schemaVersion": 1, "exportedAt": "2026-10-28T08:00:00", "account": "wxid_me",
            "conversation": {"username": username, "displayName": name, "isGroup": True},
            "messages": msgs if msgs is not None else [
                {"id": "a:b:1", "localId": 1, "serverId": 7001, "createTime": ts("2026-10-27 10:00"),
                 "createTimeText": "2026-10-27 10:00:00", "type": 1, "renderType": "text", "isSent": False,
                 "senderUsername": "wxid_a", "senderDisplayName": "张三", "content": "试了一下 Claude Code"},
                {"id": "a:b:2", "localId": 2, "serverId": 7002, "createTime": ts("2026-10-28 07:59"), "type": 49,
                 "renderType": "link", "isSent": False, "senderUsername": "wxid_b", "senderDisplayName": "李四",
                 "title": "教程", "content": "一篇教程", "url": "https://example.com/t", "linkType": "mp"}]}


def test_pasted_text_architecture_sample():
    r = parse_export(ARCH_SAMPLE.encode("utf-8"), filename=None, platform=Platform.WECHAT, group_name="AI 创作群")
    assert r.format == "pasted_text" and len(r.messages) == 1
    m = r.messages[0]
    assert m.sender_name == "🐯小象"
    assert m.sent_at.isoformat() == "2026-10-25T18:14:00+08:00"
    assert m.text == "以后每日风向标就发飞书了……" and r.group.name == "AI 创作群"
    again = parse_export(ARCH_SAMPLE.encode("utf-8"), filename=None, platform=Platform.WECHAT, group_name="AI 创作群")
    assert again.messages[0].native_id == m.native_id               # 重复导入不产生新 ID


def test_pasted_text_time_formats_and_inference():
    text = ("张三\n2026-10-25 18:14:05\n第一条\n多行正文\n\n李四\n10-25 18:20\n第二条\n"
            "王五\n18:30\n第三条\n赵六\n00:05\n跨零点\n[2026-10-26 09:00] 钱七：单行格式\n")
    r = parse_export(text.encode(), filename=None, platform=Platform.QQ, group_name="g")
    got = [(m.sender_name, m.sent_at.strftime("%m-%d %H:%M:%S"), m.text) for m in r.messages]
    assert got == [("张三", "10-25 18:14:05", "第一条\n多行正文"), ("李四", "10-25 18:20:00", "第二条"),
                   ("王五", "10-25 18:30:00", "第三条"), ("赵六", "10-26 00:05:00", "跨零点"),
                   ("钱七", "10-26 09:00:00", "单行格式")]
    assert any("推断" in w for w in r.warnings)
    dup = parse_export("甲\n10:00\n+1\n乙\n10:00\n+1\n甲\n10:00\n+1\n".encode(), filename=None,
                       platform=Platform.QQ, group_name="g")
    assert len({m.native_id for m in dup.messages}) == 3              # 相同内容依次编号，不会互相吞掉


def test_wda_json_and_zip():
    r = parse_export(json.dumps(wda_doc(), ensure_ascii=False).encode(), filename="messages.json",
                     platform=Platform.WECHAT, group_name=None)
    assert r.format == "wda_json" and r.group.native_id == "1234@chatroom" and r.group.name == "AI 创作群"
    assert [m.native_id for m in r.messages] == ["7001", "7002"]     # 与 wechat.wda 采集器的 ID 一致
    assert r.messages[1].kind is MessageKind.LINK and r.messages[1].sender_name == "李四"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("conv_1/messages.json", json.dumps(wda_doc(), ensure_ascii=False))
        zf.writestr("conv_2/messages.json", json.dumps(wda_doc("99@chatroom", "小群", wda_doc()["messages"][:1]),
                                                       ensure_ascii=False))
    z = parse_export(buf.getvalue(), filename="export.zip", platform=Platform.WECHAT, group_name=None)
    assert z.format == "wda_zip" and z.group.native_id == "1234@chatroom" and "2 个群" in z.warnings[-1]


def test_weflow_json_and_arkme():
    doc = {"weflow": {"version": "1.0.3", "exportedAt": 1, "generator": "WeFlow"},
           "session": {"accountId": "555@chatroom", "displayName": "项目群", "type": "群聊"},
           "messages": [
               {"localId": 1, "createTime": ts("2026-10-28 07:00"), "formattedTime": "2026-10-28 07:00:00",
                "type": "文本消息", "localType": 1, "content": "早", "isSend": 0, "senderUsername": "wxid_a",
                "senderDisplayName": "张三", "platformMessageId": "8001"},
               {"localId": 2, "createTime": ts("2026-10-28 07:01"), "type": "引用消息", "localType": 244813135921,
                "content": "同意", "isSend": 1, "senderUsername": "wxid_me", "senderDisplayName": "我",
                "replyToMessageId": "8001", "quotedSender": "张三", "quotedContent": "早"}]}
    r = parse_export(json.dumps(doc, ensure_ascii=False).encode(), filename="x.json", platform=Platform.WECHAT,
                     group_name=None)
    assert r.format == "weflow_json" and r.group.native_id == "555@chatroom"
    assert r.messages[0].native_id == "8001" and r.messages[1].kind is MessageKind.REPLY
    assert r.messages[1].quote_text == "张三：早" and r.messages[1].is_self
    ark = {"weflow": {"format": "arkme-json"}, "session": doc["session"],
           "senders": [{"senderID": 1, "accountId": "wxid_a", "displayName": "张三", "groupNickname": "产品"}],
           "messages": [{"localId": 1, "createTime": ts("2026-10-28 07:00"), "type": "文本消息", "localType": 1,
                         "content": "早", "isSend": 0, "senderID": 1}]}
    a = parse_export(json.dumps(ark, ensure_ascii=False).encode(), filename=None, platform=Platform.WECHAT,
                     group_name=None)
    assert a.format == "weflow_json" and a.messages[0].sender_name == "产品"


def test_chatlab_json_and_jsonl():
    doc = {"chatlab": {"version": "0.0.2", "exportedAt": 1},
           "meta": {"name": "技术群", "platform": "qq", "type": "group", "groupId": "765"},
           "members": [{"platformId": "1", "accountName": "张三", "groupNickname": "群主"}],
           "messages": [{"sender": "1", "accountName": "张三", "timestamp": ts("2026-10-28 07:00"), "type": 0,
                         "content": "大家好", "platformMessageId": "m1"},
                        {"sender": "2", "accountName": "李四", "timestamp": ts("2026-10-28 07:01"), "type": 25,
                         "content": "好", "replyToMessageId": "m1"}]}
    r = parse_export(json.dumps(doc, ensure_ascii=False).encode(), filename=None, platform=Platform.QQ, group_name=None)
    assert r.format == "chatlab" and r.group.native_id == "765" and r.messages[0].sender_name == "群主"
    assert r.messages[1].kind is MessageKind.REPLY and r.messages[1].native_id.startswith("h")
    lines = [{"_type": "header", "chatlab": doc["chatlab"], "meta": doc["meta"]},
             {"_type": "member", "platformId": "1", "accountName": "张三"},
             *[{"_type": "message", **m} for m in doc["messages"]]]
    jl = "# 注释行\n" + "\n".join(json.dumps(x, ensure_ascii=False) for x in lines)
    r2 = parse_export(jl.encode(), filename="a.jsonl", platform=Platform.QQ, group_name=None)
    assert r2.format == "chatlab" and len(r2.messages) == 2


def test_csv_chinese_and_english_headers():
    zh = "时间,群名,发送者,内容,类型\n2026-10-28 07:00:00,产品群,张三,早上好,文本\n2026/10/28 07:05,产品群,李四,[图片],图片\n"
    r = parse_export(zh.encode("utf-8-sig"), filename="chat.csv", platform=Platform.FEISHU, group_name=None)
    assert r.format == "csv" and r.group.name == "产品群" and len(r.messages) == 2
    assert r.messages[1].kind is MessageKind.IMAGE and r.messages[1].sender_name == "李四"
    en = "timestamp\tsender\tmessage\n1761606000\tAlice\thello\n1761606060\tBob\tworld\n"
    e = parse_export(en.encode("gb18030"), filename="chat.tsv", platform=Platform.QQ, group_name="Team")
    assert e.group.name == "Team" and [m.sender_name for m in e.messages] == ["Alice", "Bob"]
    multi = "日期,时间,群,昵称,消息\n2026-10-28,07:00,A群,甲,一\n2026-10-28,07:01,B群,乙,二\n2026-10-28,07:02,B群,丙,三\n"
    m = parse_export(multi.encode(), filename=None, platform=Platform.QQ, group_name=None)
    assert m.group.name == "B群" and len(m.messages) == 2 and "2 个群" in m.warnings[-1]


def test_unrecognized_content_raises_chinese():
    with pytest.raises(ImportFormatError, match="不是已知"):
        parse_export(b'{"foo": 1}', filename="x.json", platform=Platform.QQ, group_name=None)
    with pytest.raises(ImportFormatError, match="没有识别出"):
        parse_export("随便写的一段话\n没有时间".encode(), filename=None, platform=Platform.QQ, group_name=None)


def test_file_import_collector_inbox_and_processed(tmp_path):
    c = FileImportCollector(collector_ctx(tmp_path, "wechat"))
    assert c.key == "wechat.file_import"
    h = run(c.health())
    assert h.ok and h.state is Health.OK and "为空" in h.detail and (tmp_path / "inbox" / "wechat").is_dir()
    (tmp_path / "inbox" / "wechat" / "export.json").write_text(json.dumps(wda_doc(), ensure_ascii=False), "utf-8")
    (tmp_path / "inbox" / "wechat" / "notes.txt").write_text("这不是聊天记录", "utf-8")
    groups = run(c.list_groups())
    assert [g.native_id for g in groups] == ["1234@chatroom"]
    g = groups[0]
    res = run(c.fetch_messages(g, dt("2026-10-27 08:00"), dt("2026-10-28 08:00")))
    assert [m.native_id for m in res.messages] == ["7001", "7002"]
    assert any("notes.txt" in w for w in res.warnings)
    state = json.loads((tmp_path / "inbox" / "wechat" / ".processed.json").read_text("utf-8"))
    entry = next(iter(state.values()))
    assert entry["name"] == "export.json" and entry["groups"]["1234@chatroom"]["done"]
    again = run(c.fetch_messages(g, dt("2026-10-20 00:00"), dt("2026-10-29 00:00")))
    assert again.messages == []                                       # 已处理的文件不再重复读取
    qq = FileImportCollector(collector_ctx(tmp_path, "qq"))
    assert qq.key == "qq.file_import" and qq.inbox == tmp_path / "inbox" / "qq"


def test_file_import_not_done_when_file_extends_past_window(tmp_path):
    c = FileImportCollector(collector_ctx(tmp_path, "wechat"))
    c.inbox.mkdir(parents=True)
    (c.inbox / "export.json").write_text(json.dumps(wda_doc(), ensure_ascii=False), "utf-8")
    g = run(c.list_groups())[0]
    first = run(c.fetch_messages(g, dt("2026-10-27 08:00"), dt("2026-10-28 07:00")))
    assert [m.native_id for m in first.messages] == ["7001"]
    second = run(c.fetch_messages(g, dt("2026-10-28 07:00"), dt("2026-10-28 08:00")))
    assert [m.native_id for m in second.messages] == ["7002"]