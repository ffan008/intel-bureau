"""演示数据的脚本结构与群定义。"""

from __future__ import annotations

from dataclasses import dataclass, field

from bureau.contracts import Platform

SEED = 20261028


@dataclass(frozen=True)
class DemoGroup:
    short: str
    platform: Platform
    native_id: str
    name: str
    members: int
    activity: float          # 相对活跃度
    tools: tuple[str, ...]   # 闲聊里常提的工具
    topics: tuple[str, ...]  # 闲聊里常提的话题

    @property
    def key(self) -> str:
        return f"{self.platform.value}:{self.native_id}"


DEMO_GROUPS: list[DemoGroup] = [
    # 群名、昵称均为虚构；不要使用真实群聊里的名字
    DemoGroup("wx_shouhui8", Platform.WECHAT, "demo-wx-shouhui8", "水彩手绘研习社", 487, 1.10,
              ("即梦", "MJ", "Procreate", "ComfyUI"), ("手绘风", "水彩", "线稿", "绘本", "头像")),
    DemoGroup("wx_aichutu", Platform.WECHAT, "demo-wx-aichutu", "AI 出图研究所", 452, 1.20,
              ("MJ", "即梦", "可灵", "ComfyUI", "Flux"), ("出图", "风格词", "放大", "海报", "提示词")),
    DemoGroup("wx_cccamp", Platform.WECHAT, "demo-wx-cccamp", "Claude Code 实战营", 368, 1.00,
              ("Claude Code", "Codex", "Cursor", "MCP"), ("Skill", "hooks", "重构", "单测", "CLAUDE.md")),
    DemoGroup("wx_xhs", Platform.WECHAT, "demo-wx-xhs", "小红书 AI 起号互助会", 296, 0.90,
              ("小红书", "公众号", "剪映", "即梦"), ("起号", "涨粉", "流量主", "封面", "选题")),
    DemoGroup("qq_manju", Platform.QQ, "demo-qq-731205", "AI 漫剧制作交流", 1260, 1.00,
              ("即梦", "可灵", "剪映", "MJ"), ("漫剧", "配音", "镜头", "剧本", "转场")),
    DemoGroup("qq_comfy", Platform.QQ, "demo-qq-562781", "ComfyUI 工作流分享", 1835, 0.90,
              ("ComfyUI", "Flux", "LoRA", "IPAdapter"), ("显存", "节点", "工作流", "插件", "报错")),
    DemoGroup("qq_jiedan", Platform.QQ, "demo-qq-904416", "AI 副业接单群", 742, 0.80,
              ("闲鱼", "MJ", "可灵", "剪映"), ("接单", "报价", "甲方", "定金", "副业")),
    DemoGroup("fs_aigc", Platform.FEISHU, "demo-oc-aigc-studio", "AIGC 内容工作室", 38, 0.70,
              ("即梦", "可灵", "飞书多维表格", "剪映"), ("交付", "排期", "分镜", "选题会", "复盘")),
    DemoGroup("fs_agent", Platform.FEISHU, "demo-oc-agent-lab", "Agent 自动化实验室", 26, 0.70,
              ("n8n", "Dify", "Claude Code", "MCP"), ("自动化", "定时任务", "日报", "工作流", "部署")),
]

GROUP_BY_SHORT = {g.short: g for g in DEMO_GROUPS}


@dataclass(frozen=True)
class L:
    """脚本中的一行。role 是 A/B/C/D/E，同一线程内映射到不同的群成员。"""
    role: str
    text: str
    reply: int | None = None        # 引用回复第几行
    kind: str = "text"              # text / link / image / file
    url: str | None = None          # link 卡片的地址
    title: str | None = None
    media: str | None = None        # image / file：data_dir/demo_media/ 下的演示素材文件名（v2）


@dataclass(frozen=True)
class T:
    """一个对话线程脚本。days 是相对窗口的天数：0 表示最近 24 小时，-1 表示前一天。"""
    id: str
    family: str
    groups: tuple[str, ...]
    days: tuple[int, ...]
    lines: tuple[L, ...]
    hours: tuple[int, int] | None = None
    forward: tuple[str, ...] = field(default_factory=tuple)   # 把第 0 行原样转发到这些群


FAMILY_TITLES: dict[str, str] = {
    "manju_flow": "即梦首尾帧做 AI 漫剧",
    "comfy_char": "ComfyUI 角色一致性工作流",
    "shouhui": "手绘风出图与作业复盘",
    "cc_practice": "Claude Code 实战技巧",
    "agent_auto": "自动化工作流（n8n / 多维表格）",
    "gzh_money": "公众号流量主收益复盘",
    "xhs_growth": "小红书 AI 绘画号起号",
    "jiedan": "AI 接单行情",
    "style_table": "风格词对照表",
    "ad_xigao": "AI 洗稿日更公众号广告",
    "studio_rule": "内容工作室交付规范",
    "comfy_vram": "低显存跑 Flux",
    "risk_student": "代过学生认证（灰色）",
    "risk_vcard": "虚拟卡开会员（灰色）",
    "risk_matrix": "批量注册矩阵号（灰色）",
    "cc_relay": "低价 Claude 中转 API",
    "kling_news": "可灵新版本传闻",
    "mj_qa": "MJ 放大手指糊的处理",
    # v2 新增
    "avatar_prompt": "水彩头像提示词模板",
    "comfy_pack": "ComfyUI 工作流整合包",
    "seedance_x": "Seedance 多镜头一致性",
    "bitable_article": "多维表格自动化文章",
    "flux_gguf": "8G 显存跑 Flux（GGUF）",
    "risk_account": "实名号出售（违法高危）",
    "privacy_doxx": "曝光甲方个人信息（隐私）",
}
