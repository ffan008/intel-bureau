"""第三方平台集成（负责人 B）。

- ``onebot``：OneBot 11 HTTP 客户端、消息段转文本、上报验签与解析（A 调用
  ``verify_onebot_request`` / ``parse_onebot_event``）。
- ``lark_cli``：飞书官方 lark-cli 的查找、调用与错误转中文。
- ``chat_formats``：微信侧（WeChatDataAnalysis / WeFlow / ChatLab）消息字段到 ``RawMessage`` 的映射，
  采集器和文件导入共用。
- ``push_common``：推送通道共用的分段、重试、幂等账本与 Markdown→HTML。
- ``netsafe``（v2）：对外 HTTP 的 SSRF 防护（只允许 http/https 公网地址、重定向逐跳复查、限时限量）。
- ``htmltext``（v2）：HTML → 粗略 Markdown（标准库 html.parser），research 与 media 共用。
- ``common``：时间、哈希等小工具。

本包只依赖标准库、httpx、pydantic 和 ``bureau.contracts`` / ``bureau.channels.base``，
不依赖 ``bureau.core``，以免和 A 的实现互相阻塞。
"""
