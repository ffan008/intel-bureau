"""流水线阶段、Agent 映射与情报分类等常量。"""

from __future__ import annotations

STAGES: list[str] = [
    "collect", "clean", "stats", "segment", "extract", "merge",
    "score", "verify", "compose", "render", "deliver", "archive",
]

STAGE_LABELS: dict[str, str] = {
    "collect": "采集", "clean": "清洗", "stats": "统计", "segment": "切块",
    "extract": "提取", "merge": "合并", "score": "评分", "verify": "核验",
    "compose": "撰写", "render": "排版", "deliver": "投递", "archive": "归档",
}

STAGE_AGENT: dict[str, str] = {
    "collect": "SCOUT", "clean": "SWEEPER", "stats": "ANALYST", "segment": "ANALYST",
    "extract": "DECODER", "merge": "STRATEGIST", "score": "STRATEGIST", "verify": "AUDITOR",
    "compose": "WRITER", "render": "WRITER", "deliver": "COURIER", "archive": "COURIER",
}

# (代号, 中文名, 阶段, 待命时的任务描述)
AGENTS: list[tuple[str, str, list[str], str]] = [
    ("SCOUT", "侦察兵", ["collect"], "采集白名单群消息"),
    ("SWEEPER", "清道夫", ["clean"], "清洗噪声与重复转发"),
    ("ANALYST", "分析师", ["stats", "segment"], "统计热度、切分对话线程"),
    ("DECODER", "解码员", ["extract"], "从对话中提取候选情报"),
    ("STRATEGIST", "参谋", ["merge", "score"], "合并话题、打分排序"),
    ("AUDITOR", "审查官", ["verify"], "核对证据与数字"),
    ("WRITER", "主笔", ["compose", "render"], "撰写风向判断与报告"),
    ("COURIER", "通讯兵", ["deliver", "archive"], "投递报告并归档"),
]

KINDS: list[str] = ["教程方法", "工具资源", "数据复盘", "动态新闻", "观点判断", "需求机会", "风险预警", "问答精华"]

RISK_FLAGS: list[str] = ["合规风险", "账号风险", "金钱风险", "广告引流", "未核实"]
SERIOUS_RISKS: frozenset[str] = frozenset({"合规风险", "账号风险", "金钱风险", "广告引流"})

# ---------------- v2（docs/V2_KNOWLEDGE.md §2） ----------------
RISK_ILLEGAL = "违法高危"
RISK_PRIVACY = "隐私"
# 新增的类别不写进 config/taxonomy.yaml（v1 服务在读），由 v2 代码合并，见 core/taxonomy.load_taxonomy_v2
RISK_FLAGS_V2: list[str] = ["合规风险", "平台规则", "账号风险", "金钱风险", "广告引流", "版权风险", "未核实",
                            RISK_ILLEGAL, RISK_PRIVACY]
# flag / drop 策略下按旧规则处理的类别（v1 的四类 + v2 新增的两类 + 违法高危）
SERIOUS_RISKS_V2: frozenset[str] = frozenset({"合规风险", "平台规则", "账号风险", "金钱风险", "广告引流", "版权风险",
                                              RISK_ILLEGAL})
RISK_POLICIES: tuple[str, ...] = ("label", "flag", "drop")
DISCLAIMER = ("⚠️ 风险提示：以上内容整理自群聊讨论与公开资料，仅供学习研究。涉及平台规则、账号与资金的操作可能违反服务条款"
              "或带来损失，是否采用请自行判断并承担责任。")
ILLEGAL_NOTE = "该话题涉及违法高危内容，这里只记录群内讨论了什么，不做联网扩展，不提供操作步骤和链接。"

# 报告板块：key 与顺序固定（§3.1）
SECTIONS: list[tuple[str, str]] = [
    ("overview", "今日总览"), ("articles", "专题文章"), ("resources", "资源库"), ("prompts", "提示词原文"),
    ("sops", "方法与 SOP"), ("tools", "工具与模型"), ("data", "收益与数据"), ("risks", "风险与踩坑"),
    ("quotes", "金句与判断"), ("media", "图片与文档"), ("groups", "分群摘要"), ("briefs", "快讯与其余"),
]
SECTION_KEYS: list[str] = [k for k, _ in SECTIONS]
SECTION_TITLES: dict[str, str] = dict(SECTIONS)

LINK_KINDS: tuple[str, ...] = ("github", "x", "wechat_article", "netdisk", "video", "doc", "web", "other")
# 资源库分组：(分组 key, 标题, 包含的链接类型)
RESOURCE_GROUPS: list[tuple[str, str, tuple[str, ...]]] = [
    ("github", "GitHub", ("github",)), ("x", "X / 推特", ("x",)), ("wechat_article", "公众号", ("wechat_article",)),
    ("netdisk", "网盘", ("netdisk",)), ("video", "视频", ("video",)), ("doc", "文档", ("doc",)),
    ("other", "其它", ("web", "other")),
]

DEFAULT_CATEGORIES: list[str] = [
    "01 工具与资源", "02 提示词与工作流", "03 AI 创作实战", "04 流量与变现",
    "05 编程与自动化", "06 模型与平台动态", "07 需求与机会", "08 风险与避坑", "99 其他",
]

MSG_KIND_LABELS: dict[str, str] = {
    "text": "文本", "image": "图片", "link": "链接", "file": "文件", "video": "视频",
    "voice": "语音", "sticker": "表情", "card": "卡片", "forward": "合并转发", "reply": "引用回复",
    "system": "系统消息", "recall": "撤回", "redpacket": "红包", "other": "其他",
}

TREND_LABELS: dict[str, str] = {"new": "新出现", "developing": "持续发酵", "repeat": "重复"}

LIVE_PLATFORMS: list[str] = ["wechat", "qq", "feishu"]

# 采集器缺失时的中文名（注册表里的模块可能尚未交付）
ADAPTER_FALLBACK_LABELS: dict[str, str] = {
    "wechat.wda": "WeChatDataAnalysis 本地 API",
    "wechat.weflow": "WeFlow HTTP API",
    "wechat.file_import": "导入聊天记录文件",
    "qq.onebot": "NapCatQQ（OneBot 11）",
    "qq.file_import": "导入聊天记录文件",
    "feishu.lark_cli": "飞书官方 lark-cli",
    "feishu.file_import": "导入聊天记录文件",
    "demo.synthetic": "演示数据（合成）",
}

CHANNEL_FALLBACK_LABELS: dict[str, tuple[str, str]] = {
    "feishu_webhook": ("飞书群机器人（Webhook）", "飞书"),
    "feishu_app": ("飞书应用机器人（lark-cli）", "飞书"),
    "feishu_doc": ("飞书文档（实验性）", "飞书"),
    "wecom_webhook": ("企业微信群机器人", "微信"),
    "serverchan": ("Server酱", "微信"),
    "pushplus": ("PushPlus", "微信"),
    "wxpusher": ("WxPusher", "微信"),
    "qq_onebot": ("QQ（NapCat OneBot）", "QQ"),
    "email_smtp": ("邮箱（SMTP）", "邮箱"),
    "local_archive": ("本地归档", "本地"),
}
