"""qq_onebot 与 email_smtp 通道：成功、业务失败、网络失败、分段（假 NapCat / 假 SMTP）。"""

from __future__ import annotations

import json
import smtplib

from bureau.channels.email_smtp import EmailSmtpChannel
from bureau.channels.qq_onebot import MORE_NOTE, QQOneBotChannel, plan_qq_parts

from .helpers import MockHTTP, channel_ctx, make_report, ok_json, refuse, run


def qq(tmp_path, handler, settings=None):
    http = MockHTTP(handler)
    ch = QQOneBotChannel(channel_ctx(tmp_path, settings or {"target_type": "private", "target_id": "10001"},
                                     {"token": "tk"}))
    ch.transport, ch.retry_base_delay, ch.part_interval = http.transport, 0, 0
    return ch, http


def test_qq_private_success(tmp_path):
    ch, http = qq(tmp_path, lambda r: ok_json({"status": "ok", "retcode": 0, "data": {"message_id": 555}}))
    res = run(ch.send(make_report()))
    assert res.ok and res.external_id == "555"
    req = http.requests[0]
    body = json.loads(req.content)
    assert req.url.path == "/send_private_msg" and req.headers["Authorization"] == "Bearer tk"
    assert body["user_id"] == "10001" and body["message"][0]["type"] == "text"
    assert body["message"][0]["data"]["text"].startswith("情报局")


def test_qq_group_business_and_network_failure(tmp_path):
    ch, http = qq(tmp_path, lambda r: ok_json({"status": "failed", "retcode": 1404, "message": "群不存在"}),
                  {"target_type": "group", "target_id": "765"})
    res = run(ch.send(make_report()))
    assert not res.ok and http.requests[0].url.path == "/send_group_msg" and len(http.requests) == 1
    assert "群" in res.detail
    ch, http = qq(tmp_path, refuse)
    res = run(ch.send(make_report(report_id="r2")))
    assert not res.ok and res.retryable and len(http.requests) == 3 and "NapCat" in res.detail


def test_qq_segments_max_six_with_note(tmp_path):
    text = "\n".join("第%d段 " % i + "字" * 700 for i in range(30))
    parts = plan_qq_parts(text, "http://127.0.0.1:8765/#/reports/x")
    assert len(parts) == 6 and all(len(p) <= 1500 for p in parts)
    assert MORE_NOTE in parts[-1] and "http://127.0.0.1:8765" in parts[-1]
    ch, http = qq(tmp_path, lambda r: ok_json({"status": "ok", "retcode": 0, "data": {"message_id": 1}}))
    res = run(ch.send(make_report(summary_text=text)))
    assert res.ok and res.parts == 6 and len(http.requests) == 6
    texts = [json.loads(r.content)["message"][0]["data"]["text"] for r in http.requests]
    assert texts[0].startswith("[1/6] ") and all(len(t) <= 1500 for t in texts)
    assert "完整内容请在工作台查看" in texts[-1]
    assert QQOneBotChannel.part_interval == 1.5


class FakeSMTP:
    sent: list = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port

    def login(self, user, password):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append((self.host, self.port, self.user, msg))
        return {}

    def quit(self):
        pass


def mail(tmp_path, **settings):
    FakeSMTP.sent, FakeSMTP.fail_with = [], None
    base = {"username": "123@qq.com", "recipients": "a@example.com, b@example.com"}
    ch = EmailSmtpChannel(channel_ctx(tmp_path, base | settings, {"password": "authcode"}))
    ch.smtp_ssl_class, ch.smtp_class, ch.retry_base_delay = FakeSMTP, FakeSMTP, 0
    return ch


def test_email_success_html_and_attachment(tmp_path):
    ch = mail(tmp_path)
    res = run(ch.send(make_report()))
    assert res.ok
    host, port, user, msg = FakeSMTP.sent[0]
    assert (host, port, user) == ("smtp.qq.com", 465, "123@qq.com")
    assert msg["To"] == "a@example.com, b@example.com" and msg["Subject"].startswith("情报局")
    html = msg.get_body(("html",)).get_content()
    assert "<li>一条判断</li>" in html and 'href="http://127.0.0.1:8765/#/reports/r-20261028"' in html
    att = next(msg.iter_attachments())
    assert att.get_filename().endswith(".md") and "完整报告" in att.get_content()


def test_email_auth_failure_and_retry(tmp_path):
    ch = mail(tmp_path)
    FakeSMTP.fail_with = smtplib.SMTPAuthenticationError(535, b"auth failed")
    res = run(ch.send(make_report()))
    assert not res.ok and "授权码" in res.detail and not res.retryable
    ch = mail(tmp_path)
    FakeSMTP.fail_with = smtplib.SMTPServerDisconnected("closed")
    res = run(ch.send(make_report(report_id="r2")))
    assert not res.ok and res.retryable
    bad = mail(tmp_path, recipients="not-an-email")
    assert "收件人格式不正确" in run(bad.send(make_report())).detail