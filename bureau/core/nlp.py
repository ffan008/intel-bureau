"""分词与关键词：jieba + 自定义词典 + 停用词。

自定义词典里带空格的词（如 ``Claude Code``）会先在文本里替换成连写形式再分词，
最后还原成原样展示。英文词按词典里的写法统一大小写。
"""

from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Iterable

from bureau.core.textutil import URL_RE

log = logging.getLogger("bureau.nlp")

_BUILTIN_STOP = set("""
的 了 是 我 你 他 她 它 们 这 那 就 都 也 还 在 有 和 与 及 或 而 但 并 被 把 让 给 对 从 到 向 为 以 于 上 下 中 里 个 吗 呢 吧 啊 呀 哦 嗯 哈 么 着 过 得 地 很 太 更 最 又 再 才 没 不 别 要 会 能 可 想 去 来 说 看 用 做 好 多 少 大 小 一 二 三 两 几 些 每 某 各
""".split())

# 也认 v2 清洗阶段的媒体占位符：[图片#m12]、[文件:名称.pdf#m13]（保留文件名参与分词）
_PLACEHOLDER_RE = re.compile(r"\[(?:图片|表情|动画表情|语音|视频|文件|链接|卡片|聊天记录|红包|位置|名片)"
                             r"(?:[:：]([^\]#\n]{0,120}))?(?:#m\d+)?\]")
_HAS_WORD_CHAR = re.compile(r"[A-Za-z一-鿿]")
_CJK_RE = re.compile(r"[一-鿿]")
_BAD_CHARS = re.compile(r"[^\w一-鿿+#.\-]")


class NLP:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ready = False
        self.stopwords: set[str] = set(_BUILTIN_STOP)
        self.phrase_re: re.Pattern[str] | None = None
        self.phrase_canon: dict[str, str] = {}     # 小写短语 -> 连写形式
        self.display: dict[str, str] = {}          # 连写形式 -> 展示形式
        self.ascii_canon: dict[str, str] = {}      # 小写英文词 -> 词典写法
        self.dict_words: set[str] = set()
        self.idf: dict[str, float] = {}
        self.median_idf = 10.0
        self._jieba = None

    # ---------- 初始化 ----------
    def init(self, userdict: Path | None, stopwords: Path | None, cache_dir: Path | None) -> None:
        with self._lock:
            if self.ready:
                return
            import warnings
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            import jieba
            import jieba.analyse

            jieba.setLogLevel(logging.WARNING)
            if cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                jieba.dt.tmp_dir = str(cache_dir)
            jieba.initialize()
            self._jieba = jieba
            tfidf = jieba.analyse.default_tfidf
            self.idf = tfidf.idf_freq
            self.median_idf = float(tfidf.median_idf)
            if stopwords is not None and stopwords.exists():
                for line in stopwords.read_text(encoding="utf-8").splitlines():
                    w = line.strip()
                    if w and not w.startswith("#"):
                        self.stopwords.add(w.lower())
            phrases: list[str] = []
            if userdict is not None and userdict.exists():
                for line in userdict.read_text(encoding="utf-8-sig").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = re.match(r"^(.+?)(?:\s+(\d+))?(?:\s+([a-z]+))?$", line)
                    if not m:
                        continue
                    word, freq, tag = m.group(1).strip(), m.group(2), m.group(3)
                    f = int(freq) if freq else 2000
                    if " " in word:
                        joined = re.sub(r"\s+", "_", word)
                        jieba.add_word(joined, f, tag)
                        self.phrase_canon[word.lower()] = joined
                        self.display[joined] = word
                        phrases.append(word)
                    else:
                        jieba.add_word(word, f, tag)
                        if not _CJK_RE.search(word):
                            self.ascii_canon[word.lower()] = word
                    self.dict_words.add(word)
            if phrases:
                phrases.sort(key=len, reverse=True)
                pat = "|".join(re.escape(p).replace(r"\ ", r"\s*") for p in phrases)
                self.phrase_re = re.compile(rf"(?<![A-Za-z])(?:{pat})(?![A-Za-z])", re.I)
            self.ready = True

    def configure(self, userdict: Path | None, stopwords: Path | None, cache_dir: Path | None) -> None:
        """记录词典路径，首次分词时再加载（jieba 初始化约 1~2 秒）。"""
        self._cfg = (userdict, stopwords, cache_dir)

    def _ensure(self) -> None:
        if not self.ready:
            cfg = getattr(self, "_cfg", None)
            if cfg is None:
                from bureau.core.paths import resolve_paths
                p = resolve_paths()
                cfg = (p.userdict, p.stopwords, p.jieba_cache)
            self.init(*cfg)

    # ---------- 分词 ----------
    def _prep(self, text: str) -> str:
        t = URL_RE.sub(" ", text or "")
        t = _PLACEHOLDER_RE.sub(lambda m: " " + (m.group(1) or "") + " ", t)
        if self.phrase_re is not None:
            t = self.phrase_re.sub(lambda m: " " + self.phrase_canon.get(re.sub(r"\s+", " ", m.group(0).lower()),
                                                                       m.group(0)) + " ", t)
        return t

    def canon(self, tok: str) -> str | None:
        tok = tok.strip()
        if not tok:
            return None
        if tok in self.display:
            return self.display[tok]
        if _BAD_CHARS.search(tok) or not _HAS_WORD_CHAR.search(tok):
            return None
        low = tok.lower()
        if low in self.stopwords:
            return None
        if _CJK_RE.search(tok):
            if len(tok) < 2:
                return None
        elif len(tok) < 2 or tok.replace(".", "").isdigit():
            return None
        return self.ascii_canon.get(low, tok)

    def tokens(self, text: str) -> list[str]:
        self._ensure()
        assert self._jieba is not None
        out: list[str] = []
        for tok in self._jieba.lcut(self._prep(text), HMM=True):
            c = self.canon(tok)
            if c:
                out.append(c)
        return out

    def token_set(self, *texts: str) -> set[str]:
        s: set[str] = set()
        for t in texts:
            s.update(w.lower() for w in self.tokens(t))
        return s

    def idf_of(self, word: str) -> float:
        if word in self.dict_words:
            return self.median_idf * 1.15
        return float(self.idf.get(word, self.idf.get(word.lower(), self.median_idf)))

    def extract_keywords(self, texts: Iterable[str], top_k: int = 10) -> list[str]:
        tf: Counter[str] = Counter()
        for t in texts:
            tf.update(self.tokens(t))
        scored = sorted(tf.items(), key=lambda kv: kv[1] * self.idf_of(kv[0]), reverse=True)
        return [w for w, _ in scored[:top_k]]


NLP_INSTANCE = NLP()


def init_nlp(userdict: Path | None, stopwords: Path | None, cache_dir: Path | None) -> NLP:
    NLP_INSTANCE.init(userdict, stopwords, cache_dir)
    return NLP_INSTANCE


def tokens(text: str) -> list[str]:
    return NLP_INSTANCE.tokens(text)


def token_set(*texts: str) -> set[str]:
    return NLP_INSTANCE.token_set(*texts)


def keywords(texts: Iterable[str], top_k: int = 10) -> list[str]:
    return NLP_INSTANCE.extract_keywords(texts, top_k)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap(a: set[str], b: set[str]) -> float:
    """重叠系数 |A∩B| / min(|A|,|B|)，集合太小时按 3 计，避免偶然命中。"""
    if not a or not b:
        return 0.0
    return len(a & b) / max(3, min(len(a), len(b)))


def log_norm(x: float, cap: float) -> float:
    """把计数映射到 0~1（对数）。"""
    if x <= 0:
        return 0.0
    return min(1.0, math.log1p(x) / math.log1p(cap))
