"""邮箱推送（SMTP）：HTML 正文 + 完整版 Markdown 附件。

默认 QQ 邮箱 ``smtp.qq.com:465``（SSL），密码栏填 QQ 邮箱「授权码」而不是 QQ 密码。
（QQ 邮箱帮助中心页面为脚本渲染，未能抓取正文核实；以上为 QQ 邮箱公开的标准设置，见交付说明。）
smtplib 是同步库，按项目约定用 ``asyncio.to_thread`` 包装，并设置超时。
"""

from __future__ import annotations

import asyncio
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from bureau.channels.base import Channel
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, idempotency_key,
                                             markdown_to_html, report_markdown, report_text)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SMTP_TIMEOUT = 30.0
MAX_HTML_BYTES = 5 * 1024 * 1024
_WRAP = ('<!doctype html><html><head><meta charset="utf-8"></head>'
         '<body style="font-family:-apple-system,Segoe UI,Microsoft YaHei,sans-serif;line-height:1.7;color:#1f2328;'
         'max-width:760px;margin:0 auto;padding:16px">{body}'
         '<hr><p style="color:#888;font-size:12px">由「个人情报局工作台」自动发送</p></body></html>')


def _recipients(value: object) -> list[str]:
    return [x for x in re.split(r"[\s,，;；]+", str(value or "")) if x]


class EmailSmtpChannel(Channel):
    kind = "email_smtp"
    label = "邮箱（SMTP）"
    platform_label = "邮箱"
    smtp_ssl_class = smtplib.SMTP_SSL     # 测试时替换成假实现
    smtp_class = smtplib.SMTP
    retry_base_delay = 2.0

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="smtp_host", label="SMTP 服务器", default="smtp.qq.com"),
            ConfigField(key="smtp_port", label="端口", type="number", default=465),
            ConfigField(key="security", label="加密方式", type="select", default="ssl",
                        options=[{"value": "ssl", "label": "SSL（465）"}, {"value": "starttls", "label": "STARTTLS（587）"}]),
            ConfigField(key="username", label="邮箱账号", required=True, placeholder="123456@qq.com"),
            ConfigField(key="password", label="授权码", type="secret", required=True,
                        help="QQ 邮箱：设置 → 账号与安全 → 安全设置 → 开启 SMTP 服务后生成的授权码，不是 QQ 密码"),
            ConfigField(key="recipients", label="收件人", type="textarea", required=True,
                        help="多个邮箱用逗号或换行分隔"),
            ConfigField(key="sender_name", label="发件人名称", default="情报局"),
            ConfigField(key="body", label="正文", type="select", default="summary",
                        options=[{"value": "summary", "label": "推送精简版（邮件客户端显示最稳）"},
                                 {"value": "full_html", "label": "完整 HTML 报告（深色主题，部分客户端样式会丢失）"}]),
            ConfigField(key="attach_markdown", label="附带完整版 .md 附件", type="bool", default=True),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        if self.ctx.settings.get("username") and not EMAIL_RE.match(str(self.ctx.settings["username"]).strip()):
            errors.append("邮箱账号格式不正确")
        bad = [r for r in _recipients(self.ctx.settings.get("recipients")) if not EMAIL_RE.match(r)]
        if bad:
            errors.append(f"收件人格式不正确：{'、'.join(bad[:3])}")
        return errors

    def _html(self, report: ReportPayload) -> str:
        if self.ctx.settings.get("body") == "full_html" and report.html_path:
            p = Path(report.html_path)
            try:
                if p.is_file() and p.stat().st_size <= MAX_HTML_BYTES:
                    return p.read_text("utf-8")
            except OSError:
                pass
        return _WRAP.format(body=markdown_to_html(report_markdown(report)))

    def build_message(self, report: ReportPayload) -> EmailMessage:
        s = self.ctx.settings
        user = str(s["username"]).strip()
        msg = EmailMessage()
        msg["Subject"] = report.title
        msg["From"] = formataddr((str(s.get("sender_name") or "情报局"), user))
        msg["To"] = ", ".join(_recipients(s.get("recipients")))
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(idstring=idempotency_key(report, self.ctx.channel_id, max_len=40),
                                       domain=user.split("@")[-1])
        msg.set_content(report_text(report))
        msg.add_alternative(self._html(report), subtype="html")
        if s.get("attach_markdown", True) and (report.full_md or "").strip():
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", f"情报局_{report.date_label}") + ".md"
            # 用字符串形式附加，声明 charset=utf-8；字节形式会缺少 charset，客户端按 ASCII 解码会乱码
            msg.add_attachment(report.full_md, subtype="markdown", charset="utf-8", filename=name)
        return msg


    def _send_sync(self, msg: EmailMessage) -> dict[str, tuple[int, bytes]]:
        s = self.ctx.settings
        host = str(s.get("smtp_host") or "smtp.qq.com").strip()
        port = int(s.get("smtp_port") or 465)
        user = str(s["username"]).strip()
        password = str(self.ctx.secrets["password"])
        context = ssl.create_default_context()
        if str(s.get("security") or "ssl") == "starttls":
            server = self.smtp_class(host, port, timeout=SMTP_TIMEOUT)
            server.starttls(context=context)
        else:
            server = self.smtp_ssl_class(host, port, timeout=SMTP_TIMEOUT, context=context)
        try:
            server.login(user, password)
            return server.send_message(msg)
        finally:
            try:
                server.quit()
            except (smtplib.SMTPException, OSError):
                pass

    async def _send_once(self, msg: EmailMessage) -> PartOutcome:
        try:
            refused = await asyncio.to_thread(self._send_sync, msg)
        except smtplib.SMTPAuthenticationError:
            raise SendError("邮箱登录失败：账号或授权码不对（QQ 邮箱要用「授权码」，不是 QQ 密码）") from None
        except smtplib.SMTPRecipientsRefused:
            raise SendError("所有收件人都被服务器拒收，请检查收件人地址") from None
        except smtplib.SMTPSenderRefused:
            raise SendError("发件人被服务器拒绝，请确认账号已开启 SMTP 服务") from None
        except smtplib.SMTPDataError as exc:
            raise SendError(f"邮件被服务器拒绝（{exc.smtp_code}），可能被判为垃圾邮件或超出发送频率",
                            retryable=400 <= int(exc.smtp_code or 0) < 500) from None
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, TimeoutError):
            raise SendError("连接邮件服务器超时或被断开", retryable=True) from None
        except ssl.SSLError:
            raise SendError("与邮件服务器的加密握手失败：465 端口选 SSL，587 端口选 STARTTLS") from None
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"发送邮件失败（{type(exc).__name__}），请检查服务器地址和端口", retryable=True) from None
        note = f"{len(refused)} 个收件人被拒收" if refused else None
        return PartOutcome(external_id=str(msg["Message-ID"]), note=note)

    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        msg = self.build_message(report)
        return await deliver_parts(DeliveryPlan(self, report, [report.title + "\n" + report_text(report)], unit="封邮件"),
                                   lambda _i, _t: self._send_once(msg))