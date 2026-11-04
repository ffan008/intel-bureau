"""文本工具：URL 抽取、归一化、脱敏、数字抽取、宽度计算。"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

URL_RE = re.compile(r"https?://[^\s<>\"'（）()【】\[\]{}，。；！？、　]+", re.I)
_TRAILING = ".,;:!?)]}>'\"，。；：！？）】》」』…"

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s\W_]+", re.U)
_BRACKET_EMOJI_RE = re.compile(r"\[[一-龥a-zA-Z]{1,6}\]")

# 脱敏规则（URL 区间内不处理）
_DESENS: dict[str, tuple[re.Pattern[str], str]] = {
    "email": (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱]"),
    "idcard": (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证]"),
    "bankcard": (re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"), "[银行卡]"),
    "phone": (re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"), "[手机号]"),
    "wechat_id": (re.compile(r"(?<![A-Za-z0-9])((?:微信号?|加[vV微]|[vV][xX]?|[wW][xX])(?:\s*[:：]\s*|\s+))"
                             r"[A-Za-z][-_A-Za-z0-9]{5,19}(?![A-Za-z0-9])"),
                  r"\1[微信号]"),
}
DESENS_ORDER = ("email", "idcard", "bankcard", "phone", "wechat_id")

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*(?:\.\d+)?")


def extract_urls(text: str) -> list[str]:
    out: list[str] = []
    for m in URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(_TRAILING)
        if len(u) > 10 and u not in out:
            out.append(u)
    return out


def norm_url(url: str) -> str:
    return url.strip().rstrip("/").lower()


def collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def strip_ws(text: str) -> str:
    """去掉全部空白（证据比对用）。"""
    return _WS_RE.sub("", unicodedata.normalize("NFKC", text or ""))


def norm_for_dedupe(text: str) -> str:
    """去重键：去掉 URL 外的空白和标点，统一大小写与全半角。"""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = _BRACKET_EMOJI_RE.sub("", t)
    return _PUNCT_RE.sub("", t)


def is_emoji_only(text: str) -> bool:
    t = _BRACKET_EMOJI_RE.sub("", text or "")
    t = _WS_RE.sub("", t)
    if not t:
        return True
    for ch in t:
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "N")):
            return False
    return True


def info_chars(text: str) -> int:
    """有效字符数：字母、数字、汉字。"""
    t = _BRACKET_EMOJI_RE.sub("", text or "")
    return sum(1 for ch in t if unicodedata.category(ch).startswith(("L", "N")))


def desensitize(text: str, kinds: Iterable[str]) -> tuple[str, int]:
    """按配置脱敏，返回 (新文本, 替换次数)。URL 区间保持不变。"""
    kinds = [k for k in DESENS_ORDER if k in set(kinds)]
    if not text or not kinds:
        return text, 0
    spans = [(m.start(), m.end()) for m in URL_RE.finditer(text)]
    pieces: list[str] = []
    last = 0
    for s, e in spans:
        pieces.append(text[last:s])
        pieces.append("\x00URL\x00" + text[s:e] + "\x00")
        last = e
    pieces.append(text[last:])
    total = 0
    out: list[str] = []
    for p in pieces:
        if p.startswith("\x00URL\x00"):
            out.append(p[5:-1])
            continue
        for k in kinds:
            pat, repl = _DESENS[k]
            p, n = pat.subn(repl, p)
            total += n
        out.append(p)
    return "".join(out), total


def numbers_in(text: str) -> list[str]:
    """抽出文本中的数字（去掉千分位逗号）。只统计两位以上或带小数的数，单个数字常是序号。"""
    out: list[str] = []
    for m in _NUM_RE.finditer(text or ""):
        raw = m.group(0).replace(",", "")
        if raw.count(".") > 1:
            continue
        digits = raw.replace(".", "")
        if len(digits) < 2 and "." not in raw:
            continue
        if raw not in out:
            out.append(raw)
    return out


def number_supported(num: str, source_text: str) -> bool:
    """数字是否在原文里出现（忽略千分位逗号与空白）。"""
    src = strip_ws(source_text).replace(",", "").replace("，", "")
    if num in src:
        return True
    if num.endswith(".0") and num[:-2] in src:
        return True
    return False


_CODE_RE = re.compile(r"(?:提取码|提取碼|访问码|密码|口令|(?<![A-Za-z])pwd)\s*[:：=]?\s*([A-Za-z0-9]{4,8})(?![A-Za-z0-9])", re.I)
_PWD_QS = re.compile(r"[?&](?:pwd|password)=([A-Za-z0-9]{4,8})(?![A-Za-z0-9])", re.I)


def share_code(text: str, url: str | None = None) -> str | None:
    """网盘提取码（原文照录）：先看链接里的 ?pwd=，再看这条链接之后、下一条链接之前的「提取码 xxxx」。"""
    if url:
        m = _PWD_QS.search(url)
        if m:
            return m.group(1)
    t = text or ""
    start, end = 0, len(t)
    if url and url in t:
        start = t.find(url) + len(url)
        nxt = URL_RE.search(t, start)
        end = nxt.start() if nxt else len(t)
    m = _CODE_RE.search(t, start, end)
    if m is None and url and url in t:
        before = t[:t.find(url)]
        m = None if URL_RE.search(before) else _CODE_RE.search(before)     # 「提取码 xxxx：链接」的写法
    return m.group(1) if m else None


def fmt_int(n: int | float) -> str:
    return f"{int(round(n)):,}"


def fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def truncate(text: str, n: int, ellipsis: str = "…") -> str:
    text = text or ""
    return text if len(text) <= n else text[: max(0, n - len(ellipsis))] + ellipsis


def display_width(text: str) -> int:
    w = 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def first_clause(text: str, max_len: int = 28) -> str:
    """取第一句（标题用），保持原文。"""
    t = collapse_ws(URL_RE.sub("", text or ""))
    t = t.lstrip("【[（(#*>-—·•、 ").strip()
    for sep in ("。", "！", "？", "!", "?", "\n", "；", ";"):
        idx = t.find(sep)
        if 4 <= idx:
            t = t[:idx]
            break
    if len(t) > max_len:
        cut = max((t.rfind(c, 0, max_len) for c in "，,：:、 "), default=-1)
        t = t[:cut] if cut >= 8 else t[:max_len]
    return t.strip(" ，,：:、")
