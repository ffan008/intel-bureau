"""feishu_app / feishu_doc：通过假 lark-cli 校验参数、相对路径、幂等键、成功 / 业务失败 / 网络失败 / 分段。"""

from __future__ import annotations

from pathlib import Path

from bureau.channels.feishu_app import FeishuAppChannel
from bureau.channels.feishu_doc import FeishuDocChannel
from bureau.integrations.lark_cli import LarkCli, LarkCliError

from .helpers import FakeLark, channel_ctx, lark_error, make_report, run

SEND_OK = {"message_id": "om_sent", "chat_id": "oc_x", "create_time": "1761606000"}
LONG_MD = "\n".join(f"- 第 {i} 条：" + "长内容" * 40 for i in range(300))


def app(tmp_path, routes, settings=None):
    fake = FakeLark(routes)
    ch = FeishuAppChannel(channel_ctx(tmp_path, settings or {"target_type": "user_id", "target_id": "ou_me"}))
    ch.cli, ch.retry_base_delay, ch.part_interval = LarkCli(path="C:/fake/lark-cli.exe", runner=fake), 0, 0
    return ch, fake


def test_app_success_args_relative_path_and_key(tmp_path):
    ch, fake = app(tmp_path, [(("im", "+messages-send"), SEND_OK)])
    res = run(ch.send(make_report()))
    assert res.ok and res.external_id == "om_sent"
    call = fake.calls[0]
    args = call["args"]
    assert args[:4] == ["im", "+messages-send", "--as", "bot"]
    assert args[args.index("--user-id") + 1] == "ou_me"
    assert args[args.index("--markdown") + 1] == "@report.md"            # 只用相对文件名
    key = args[args.index("--idempotency-key") + 1]
    assert len(key) <= 50 and key.startswith("ib-")
    cwd = Path(call["cwd"])
    assert cwd.parent == tmp_path / "tmp" and not cwd.exists()           # 在 data/tmp 下建临时目录，用完删除
    assert "今日风向" in call["files"]["report.md"] and "r-20261028" in call["files"]["report.md"]


def test_app_group_target_and_validation(tmp_path):
    ch, fake = app(tmp_path, [(("im",), SEND_OK)], {"target_type": "chat_id", "target_id": "oc_group"})
    assert run(ch.send(make_report())).ok and "--chat-id" in fake.calls[0]["args"]
    bad, _ = app(tmp_path, [], {"target_type": "chat_id", "target_id": "ou_wrong"})
    res = run(bad.send(make_report()))
    assert not res.ok and "oc_" in res.detail


def test_app_business_failure_bot_not_in_chat(tmp_path):
    ch, fake = app(tmp_path, [(("im",), lark_error("api", "Bot is not in the chat", code=230002, identity="bot"))])
    res = run(ch.send(make_report()))
    assert not res.ok and "机器人" in res.detail and len(fake.calls) == 1


def test_app_network_failure_retries(tmp_path):
    ch, fake = app(tmp_path, [(("im",), LarkCliError("lark-cli 执行超时", kind="timeout", retryable=True))])
    res = run(ch.send(make_report()))
    assert not res.ok and res.retryable and len(fake.calls) == 3


def test_app_splits_long_report_with_distinct_keys(tmp_path):
    ch, fake = app(tmp_path, [(("im",), SEND_OK)])
    res = run(ch.send(make_report(summary_md=LONG_MD)))
    assert res.ok and res.parts == len(fake.calls) > 1
    keys = [c["args"][c["args"].index("--idempotency-key") + 1] for c in fake.calls]
    assert len(set(keys)) == len(keys)
    assert all(len(c["files"]["report.md"].encode("utf-8")) <= 20000 + 20 for c in fake.calls)


def doc(tmp_path, routes, settings=None):
    fake = FakeLark(routes)
    ch = FeishuDocChannel(channel_ctx(tmp_path, settings or {"identity": "user", "parent_token": "wikcnXYZ"}))
    ch.cli, ch.retry_base_delay = LarkCli(path="C:/fake/lark-cli.exe", runner=fake), 0
    return ch, fake


def test_doc_success_returns_link_once(tmp_path):
    data = {"document": {"document_id": "doxcn1", "url": "https://x.feishu.cn/docx/doxcn1"}, "warnings": [], "tips": ""}
    ch, fake = doc(tmp_path, [(("docs", "+create"), data)])
    report = make_report(title="情报局 · 每日风向标 | 2026-10-28")
    res = run(ch.send(report))
    assert res.ok and res.external_id == "https://x.feishu.cn/docx/doxcn1" and "文档链接" in res.detail
    args = fake.calls[0]["args"]
    assert args[args.index("--content") + 1] == "@report.md" and args[args.index("--doc-format") + 1] == "markdown"
    assert args[args.index("--parent-token") + 1] == "wikcnXYZ"
    assert "|" not in args[args.index("--title") + 1]                   # 命令行特殊字符已替换
    assert "完整报告" in fake.calls[0]["files"]["report.md"]
    assert run(ch.send(report)).ok and len(fake.calls) == 1              # 同一报告只建一次文档


def test_doc_failures(tmp_path):
    ch, fake = doc(tmp_path, [(("docs",), lark_error("authorization", "denied", subtype="missing_scope",
                                                      missing_scopes=["docx:document:create"]))])
    res = run(ch.send(make_report()))
    assert not res.ok and "docx:document:create" in res.detail and len(fake.calls) == 1
    ch, fake = doc(tmp_path, [(("docs",), LarkCliError("超时", kind="timeout", retryable=True))])
    res = run(ch.send(make_report(report_id="r2")))
    assert not res.ok and "可能已经建好" in res.detail and len(fake.calls) == 1    # 结果不明时不重试，避免重复建文档