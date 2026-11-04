"""飞书应用机器人：通过 lark-cli 以机器人身份私聊用户（open_id）或发到群（chat_id）。

按 lark-cli 1.0.97 内置技能 lark-im-messages-send 与 ``im +messages-send --help`` 核实：
- ``lark-cli im +messages-send --as bot (--user-id ou_xxx | --chat-id oc_xxx) --markdown @<相对路径>
  --idempotency-key <≤50 字符>``；--markdown 会转成 post 富文本，``@file`` 只接受当前目录下的相对路径。
- 同一幂等键 1 小时内只发送一次；成功返回 data.message_id / chat_id / create_time。
- 以机器人身份发消息前，机器人必须已在目标群里，或与目标用户已有单聊关系（用户在应用可用范围内）。
做法：在 data/tmp/ 下建临时目录写入 Markdown 文件，以该目录为 cwd 运行，参数里只用文件名。
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.core.platform_hints import LARK_CLI_INSTALL
from bureau.integrations.lark_cli import LarkCli, LarkCliError
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, idempotency_key,
                                             report_markdown)

PART_BYTES = 20000               # post 消息体上限约 30 KB，留出转换余量


class FeishuAppChannel(Channel):
    kind = "feishu_app"
    label = "飞书应用机器人（lark-cli）"
    platform_label = "飞书"
    cli: LarkCli | None = None    # 测试时注入
    retry_base_delay = 1.0
    part_interval = 0.5

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="target_type", label="发送到", type="select", default="user_id",
                        options=[{"value": "user_id", "label": "私聊某人（open_id，ou_ 开头）"},
                                 {"value": "chat_id", "label": "群聊（chat_id，oc_ 开头）"}]),
            ConfigField(key="target_id", label="接收方 ID", required=True, placeholder="ou_… 或 oc_…",
                        help="自己的 open_id 可用 `lark-cli auth status` 查看；群 ID 可用 `lark-cli im +chat-search --query 群名`"),
            ConfigField(key="cli_path", label="lark-cli 路径", placeholder="留空自动查找"),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        ttype = str(self.ctx.settings.get("target_type") or "user_id")
        tid = str(self.ctx.settings.get("target_id") or "").strip()
        if tid:
            prefix = "ou_" if ttype == "user_id" else "oc_"
            if not tid.startswith(prefix):
                errors.append(f"接收方 ID 应以 {prefix} 开头")
        return errors

    def _cli(self) -> LarkCli:
        if self.cli is None:
            self.cli = LarkCli(cli_path=str(self.ctx.settings.get("cli_path") or "") or None, timeout=60.0)
        return self.cli


    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        cli = self._cli()
        if not cli.available:
            return self.result(False, f"没有找到 lark-cli，请{LARK_CLI_INSTALL}")
        ttype = str(self.ctx.settings.get("target_type") or "user_id")
        flag = "--user-id" if ttype == "user_id" else "--chat-id"
        target = str(self.ctx.settings["target_id"]).strip()
        md = report_markdown(report)
        # v2：文档类通道（飞书知识库）先投递，链接在 doc_links 里；正文还没带上时补一行「查看今日风向标」
        links = report.doc_links or {}
        doc_url = str(links.get("feishu_doc") or next((v for v in links.values() if v), "") or "").strip()
        if doc_url.startswith("https://") and doc_url not in md:
            md = md.rstrip() + f"\n\n👉 [查看今日风向标]({doc_url})"
        if not md.lstrip().startswith("#"):
            md = f"## {report.title}\n\n{md}"
        parts = split_text(md, PART_BYTES, measure="bytes")
        total = len(parts)
        tmp_root = Path(self.ctx.data_dir) / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        async def send_one(i: int, text: str) -> PartOutcome:
            body = text if total == 1 else f"（{i + 1}/{total}）\n{text}"
            work = Path(tempfile.mkdtemp(prefix="feishu-app-", dir=tmp_root))
            try:
                (work / "report.md").write_text(body, encoding="utf-8")
                args = ["im", "+messages-send", "--as", "bot", flag, target, "--markdown", "@report.md",
                        "--idempotency-key", idempotency_key(report, self.ctx.channel_id, i), "--format", "json"]
                try:
                    data = await cli.run(args, cwd=str(work), timeout=60.0, identity="bot")
                except LarkCliError as exc:
                    hint = f"（{exc.hint}）" if exc.hint else ""
                    if exc.kind == "not_in_chat" or "not in" in exc.message:
                        hint = "（机器人必须已在目标群里；私聊时对方要在应用的可用范围内）"
                    raise SendError(exc.message + hint, retryable=exc.retryable, code=exc.code) from None
            finally:
                shutil.rmtree(work, ignore_errors=True)
            return PartOutcome(external_id=str((data or {}).get("message_id") or "") or None)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条消息", interval=self.part_interval),
                                   send_one)