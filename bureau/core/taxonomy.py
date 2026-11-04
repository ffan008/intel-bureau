"""分类体系：读取 config/taxonomy.yaml，提供规则分类、风险词、工具名识别。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from bureau.core.constants import DEFAULT_CATEGORIES, KINDS, RISK_FLAGS


@dataclass
class Taxonomy:
    categories: list[dict[str, Any]] = field(default_factory=list)   # [{label, keywords}]
    kinds: list[str] = field(default_factory=lambda: list(KINDS))
    risk_flags: list[str] = field(default_factory=lambda: list(RISK_FLAGS))
    risk_lexicon: dict[str, list[str]] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    cues: dict[str, list[str]] = field(default_factory=dict)
    privacy_cues: list[str] = field(default_factory=list)      # v2：判断"内容主要是某个普通人的隐私"

    @property
    def labels(self) -> list[str]:
        return [c["label"] for c in self.categories] or list(DEFAULT_CATEGORIES)

    @property
    def other_label(self) -> str:
        return next((c for c in self.labels if c.startswith("99")), self.labels[-1])

    def normalize_category(self, value: str | None) -> str:
        """把模型给的分类对齐到分类表（接受 "02"、"提示词与工作流"、"02 提示词与工作流"）。"""
        v = (value or "").strip()
        if not v:
            return self.other_label
        for lab in self.labels:
            code, _, name = lab.partition(" ")
            if v == lab or v == code or v == name or v.replace(" ", "") == lab.replace(" ", ""):
                return lab
        for lab in self.labels:
            _, _, name = lab.partition(" ")
            if name and (name in v or v in name):
                return lab
        return self.other_label

    def classify(self, text: str) -> str:
        low = text.lower()
        best, best_hits = self.other_label, 0
        for c in self.categories:
            hits = sum(1 for k in c["keywords"] if k.lower() in low)
            if hits > best_hits:
                best, best_hits = c["label"], hits
        return best

    def risks_in(self, text: str) -> list[str]:
        low = text.lower()
        return [flag for flag in self.risk_flags if any(w.lower() in low for w in self.risk_lexicon.get(flag, []))]

    def tools_in(self, text: str) -> list[str]:
        out: list[str] = []
        for t in self.tools:
            pat = re.escape(t)
            if re.fullmatch(r"[A-Za-z0-9 .]+", t):
                pat = rf"(?<![A-Za-z]){pat}(?![A-Za-z])"
            if re.search(pat, text, re.I) and t not in out:
                out.append(t)
        # 去掉被更长工具名包含的短名（如 "Claude" 与 "Claude Code"）
        return [t for t in out if not any(t != o and t.lower() in o.lower() for o in out)]

    def cue_hits(self, text: str, group: str) -> int:
        return sum(1 for w in self.cues.get(group, []) if w in text)


def load_taxonomy(path: Path) -> Taxonomy:
    return _load(str(path), path.stat().st_mtime if path.exists() else 0.0)


# ---------------- v2：新增风险类别（不写进 taxonomy.yaml，v1 服务还在读它） ----------------
V2_RISK_LEXICON: dict[str, list[str]] = {
    # 只收比较确定的说法；泛词（如单独的"诈骗""未成年"）在提醒类消息里也常见，交给模型判断
    "违法高危": ["代过学生认证", "代过认证", "假学籍", "伪造学籍", "办假证", "伪造证件", "代办资质", "盗号", "洗号",
                 "收号", "卖号", "买卖账号", "实名号出售", "出售实名号", "卖实名号", "洗钱", "跑分平台", "代收款",
                 "赌博", "博彩", "赌球",
                 "色情传播", "卖片", "裸聊", "诱导未成年", "杀猪盘", "刷单返利"],
    "平台规则": ["限流", "违规", "下架", "封禁", "社区规范", "判原创", "原创失败", "AI 合成", "AI合成", "内容含 AI",
                 "平台规则", "审核不过", "降权"],
    "版权风险": ["侵权", "版权", "盗版", "洗稿", "去水印", "商用授权", "授权范围", "搬运"],
}
V2_PRIVACY_CUES: list[str] = ["电话", "手机号", "住址", "住在", "家住", "身份证", "大家注意这个人", "曝光", "挂人",
                              "老赖", "欠款不还", "欠钱", "跑路的甲方", "人肉"]


def load_taxonomy_v2(path: Path, extra_path: Path | None = None) -> Taxonomy:
    """v1 分类体系 + v2 风险类别。extra_path（config/taxonomy_v2.yaml）存在时，其中的词表追加到默认词表后面。"""
    from bureau.core.constants import RISK_FLAGS_V2

    base = load_taxonomy(path)
    extra: dict[str, Any] = {}
    if extra_path is not None and extra_path.exists():
        try:
            extra = yaml.safe_load(extra_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            extra = {}
    flags = list(dict.fromkeys([*base.risk_flags, *RISK_FLAGS_V2, *[str(x) for x in extra.get("risk_flags") or []]]))
    lex = {k: list(v) for k, v in base.risk_lexicon.items()}
    for src in (V2_RISK_LEXICON, extra.get("risk_lexicon") or {}):
        for k, words in src.items():
            cur = lex.setdefault(str(k), [])
            cur.extend(str(w) for w in (words or []) if str(w) not in cur)
    cues = list(dict.fromkeys([*V2_PRIVACY_CUES, *[str(x) for x in extra.get("privacy_cues") or []]]))
    return Taxonomy(categories=base.categories, kinds=base.kinds, risk_flags=flags, risk_lexicon=lex, tools=base.tools,
                    cues=base.cues, privacy_cues=cues)


@lru_cache(maxsize=4)
def _load(path: str, _mtime: float) -> Taxonomy:
    p = Path(path)
    data: dict[str, Any] = {}
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cats = []
    for c in data.get("categories") or []:
        label = f"{c.get('id', '').strip()} {c.get('name', '').strip()}".strip()
        cats.append({"label": label, "keywords": [str(k) for k in (c.get("keywords") or [])]})
    if not cats:
        cats = [{"label": lab, "keywords": []} for lab in DEFAULT_CATEGORIES]
    return Taxonomy(
        categories=cats,
        kinds=[str(k) for k in (data.get("kinds") or KINDS)],
        risk_flags=[str(k) for k in (data.get("risk_flags") or RISK_FLAGS)],
        risk_lexicon={str(k): [str(w) for w in (v or [])] for k, v in (data.get("risk_lexicon") or {}).items()},
        tools=[str(t) for t in (data.get("tools") or [])],
        cues={str(k): [str(w) for w in (v or [])] for k, v in (data.get("cues") or {}).items()},
    )
