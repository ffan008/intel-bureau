"""知识库存储（docs/V2_KNOWLEDGE.md §3.3）：kb_articles 存当前版本，kb_versions 存每次写入时的快照。

同一话题再出现时按话题指纹（或关键词重叠、共享链接）匹配到已有条目并合并：
- 同一天重跑：刷新当天的正文，不重复追加；
- 之后的日子：追加一节「{日期} 更新」，来源合并；
每次写入都记一条版本。scope 区分 live / demo，互不污染。
"""

from __future__ import annotations

import re
import secrets
from collections import Counter
from typing import Any, Iterable

from bureau.core.store.base import jdump, jload

_JSON_COLS = (("tags", []), ("risk_flags", []), ("keywords", []), ("links", []), ("sources", []))
_UPDATE_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) 更新[ \t]*$", re.M)
MATCH_THRESHOLD = 0.5
_SUMMARY_COLS = ("a.rid, a.id, a.scope, a.title, a.category, a.tags, a.hook, a.risk_flags, a.sources, a.first_day, "
                 "a.last_day, a.created_at, a.updated_at, "
                 "(SELECT COUNT(*) FROM kb_versions v WHERE v.kb_id=a.id) AS n_versions")


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    for k, d in _JSON_COLS:
        if k in row:
            row[k] = jload(row.get(k), d)
    return row


# ---------------- 正文合并（纯函数） ----------------
def split_updates(body: str) -> tuple[str, dict[str, str]]:
    """正文 → (基础正文, {日期: 该日更新的内容})。"""
    body = body or ""
    marks = list(_UPDATE_RE.finditer(body))
    if not marks:
        return body.rstrip(), {}
    ups: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        ups[m.group(1)] = body[m.end():end].strip()
    return body[:marks[0].start()].rstrip(), ups


def update_section(article_md: str) -> str:
    """当天的专题正文 → 「{日期} 更新」一节：去掉一级标题，其余标题降一级（代码块里不动）。"""
    lines = (article_md or "").splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    out: list[str] = []
    fence = False
    for ln in lines:
        if ln.lstrip().startswith(("```", "~~~")):
            fence = not fence
        elif not fence and re.match(r"^#{2,5} ", ln):
            ln = "#" + ln
        out.append(ln)
    return "\n".join(out).strip()


def merge_body(old_body: str, first_day: str, new_md: str, day: str) -> str:
    """把当天的专题正文并入已有条目。首日重跑替换基础正文；其它日子替换或追加「{day} 更新」一节。"""
    base, ups = split_updates(old_body)
    if day == first_day:
        base = (new_md or "").rstrip()
    else:
        ups[day] = update_section(new_md)
    parts = [base] + [f"## {d} 更新\n\n{ups[d]}" for d in sorted(ups) if d != first_day]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


def merge_sources(old: list[dict[str, Any]], new: Iterable[dict[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    seen = {(s.get("group_name"), s.get("sender"), str(s.get("sent_at") or "")[:16]) for s in old}
    out = list(old)
    for s in new:
        k = (s.get("group_name"), s.get("sender"), str(s.get("sent_at") or "")[:16])
        if k not in seen:
            seen.add(k)
            out.append({x: s.get(x) for x in ("group_name", "platform", "sender", "sent_at") if s.get(x) is not None})
    return out[-limit:]


def similarity(fp: str, keywords: Iterable[str], links: Iterable[str], cand: dict[str, Any]) -> float:
    """话题指纹相同 → 1；否则看核心词重叠（至少 3 个共同词）与共享链接。"""
    if fp and fp == cand.get("fingerprint"):
        return 1.0
    a = {str(k).lower() for k in keywords if k}
    b = {str(k).lower() for k in cand.get("keywords") or [] if k}
    sim = 0.0
    shared = a & b
    if len(shared) >= 3:
        sim = len(shared) / max(3, min(len(a), len(b)))
    la = {str(u).strip().rstrip("/").lower() for u in links if u}
    lb = {str(u).strip().rstrip("/").lower() for u in cand.get("links") or [] if u}
    if la & lb and len(shared) >= 1:
        sim = max(sim, 0.8)
    return sim


def _note(created: bool, same_day: bool, day: str, report_id: str, added: int) -> str:
    if created:
        return f"{day} 新建（报告 {report_id}）"
    if same_day:
        return f"{day} 同日重跑，刷新当天内容（报告 {report_id}）"
    return f"{day} 合并更新：新增来源 {added} 条（报告 {report_id}）"


class KbMixin:
    db: Any
    now_iso: Any

    # ---------------- 写入 ----------------
    def kb_match(self, scope: str, fingerprint: str, keywords: list[str], links: list[str],
                 exclude: set[str] | None = None) -> tuple[dict[str, Any] | None, float]:
        rows = self.db.query("SELECT id, fingerprint, keywords, links, first_day FROM kb_articles WHERE scope=?", (scope,))
        best, best_sim = None, 0.0
        for r in rows:
            if exclude and r["id"] in exclude:
                continue
            r = _decode(r) or r
            sim = similarity(fingerprint, keywords, links, r)
            if sim > best_sim:
                best, best_sim = r, sim
        return (best, best_sim) if best_sim >= MATCH_THRESHOLD else (None, best_sim)

    def kb_upsert(self, scope: str, art: dict[str, Any], *, day: str, report_id: str,
                  claimed: set[str] | None = None) -> tuple[str, str]:
        """写入一篇专题。art：title / category / tags / hook / risk_flags / fingerprint / keywords / links / body_md /
        sources。claimed 是本次运行已经合并过的条目（同一次运行里两篇不并进同一条）。返回 (kb_id, created|merged)。"""
        now = self.now_iso()
        kws = [str(k).lower() for k in art.get("keywords") or []][:60]
        links = [str(u) for u in art.get("links") or []][:40]
        target, _sim = self.kb_match(scope, str(art.get("fingerprint") or ""), kws, links, claimed)
        with self.db.tx():
            if target is None:
                kb_id = f"kb-{day.replace('-', '')}-{secrets.token_hex(3)}"
                body = (art.get("body_md") or "").rstrip() + "\n"
                sources = merge_sources([], art.get("sources") or [])
                self.db.execute(
                    "INSERT INTO kb_articles(id, scope, title, category, tags, hook, risk_flags, fingerprint, keywords, "
                    "links, body_md, sources, first_day, last_day, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (kb_id, scope, art.get("title") or "未命名", art.get("category") or "", jdump(art.get("tags") or []),
                     art.get("hook") or "", jdump(art.get("risk_flags") or []), art.get("fingerprint") or "",
                     jdump(kws), jdump(links), body, jdump(sources), day, day, now, now))
                note, status, title = _note(True, False, day, report_id, len(sources)), "created", art.get("title") or ""
            else:
                kb_id = target["id"]
                cur = _decode(self.db.query_one("SELECT * FROM kb_articles WHERE id=?", (kb_id,))) or {}
                body = merge_body(cur.get("body_md", ""), cur.get("first_day", day), art.get("body_md") or "", day)
                sources = merge_sources(cur.get("sources") or [], art.get("sources") or [])
                added = len(sources) - len(cur.get("sources") or [])
                tags = list(dict.fromkeys([*(cur.get("tags") or []), *(art.get("tags") or [])]))[:12]
                flags = list(dict.fromkeys([*(cur.get("risk_flags") or []), *(art.get("risk_flags") or [])]))
                kw_all = list(dict.fromkeys([*(cur.get("keywords") or []), *kws]))[-80:]
                links_all = list(dict.fromkeys([*(cur.get("links") or []), *links]))[-60:]
                self.db.execute(
                    "UPDATE kb_articles SET tags=?, hook=?, risk_flags=?, keywords=?, links=?, body_md=?, sources=?, "
                    "last_day=?, updated_at=? WHERE id=?",
                    (jdump(tags), art.get("hook") or cur.get("hook") or "", jdump(flags), jdump(kw_all), jdump(links_all),
                     body, jdump(sources), max(cur.get("last_day") or day, day), now, kb_id))
                same = day == cur.get("first_day") or day == cur.get("last_day")
                note, status, title = _note(False, same, day, report_id, added), "merged", cur.get("title") or ""
            self.db.execute("INSERT INTO kb_versions(kb_id, report_id, day, note, title, body_md, created_at) "
                            "VALUES(?,?,?,?,?,?,?)", (kb_id, report_id, day, note, title, body, now))
        if claimed is not None:
            claimed.add(kb_id)
        return kb_id, status

    # ---------------- 读取 ----------------
    def kb_get(self, kb_id: str) -> dict[str, Any] | None:
        row = _decode(self.db.query_one("SELECT * FROM kb_articles WHERE id=?", (kb_id,)))
        if row is not None:
            row["n_versions"] = int(self.db.scalar("SELECT COUNT(*) FROM kb_versions WHERE kb_id=?", (kb_id,), 0))
        return row

    def kb_versions(self, kb_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT id, kb_id, report_id, day, note, title, created_at FROM kb_versions "
                             "WHERE kb_id=? ORDER BY id", (kb_id,))

    def _kb_rows(self, scope: str, q: str | None, category: str | None) -> list[dict[str, Any]]:
        where, params = ["a.scope=?"], [scope]
        q = (q or "").strip()
        join = ""
        if q:
            if getattr(self.db, "kb_fts_enabled", False) and (self.db.kb_fts_tokenizer != "trigram" or len(q) >= 3):
                join = "JOIN kb_fts ON kb_fts.rowid=a.rid"
                where.append("kb_fts MATCH ?")
                params.append('"' + q.replace('"', '""') + '"')
            else:
                where.append("(a.title LIKE ? OR a.body_md LIKE ? OR a.tags LIKE ?)")
                params += [f"%{q}%"] * 3
        if category:
            where.append("a.category=?")
            params.append(category)
        rows = self.db.query(f"SELECT {_SUMMARY_COLS} FROM kb_articles a {join} WHERE {' AND '.join(where)} "
                             "ORDER BY a.updated_at DESC, a.rid DESC", params)
        return [_decode(r) for r in rows]  # type: ignore[misc]

    def kb_list(self, scope: str, *, q: str | None = None, category: str | None = None, tag: str | None = None,
                limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = self._kb_rows(scope, q, category)
        if tag:
            rows = [r for r in rows if tag in (r.get("tags") or [])]
        return rows[offset:offset + limit], len(rows)

    def kb_facets(self, scope: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows = self.db.query("SELECT category, tags FROM kb_articles WHERE scope=?", (scope,))
        cats: Counter[str] = Counter(r["category"] for r in rows if r["category"])
        tags: Counter[str] = Counter(t for r in rows for t in jload(r["tags"], []) if t)
        return ([{"name": k, "count": v} for k, v in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))],
                [{"name": k, "count": v} for k, v in sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[:60]])

    def kb_counts(self, scope: str, today: str) -> dict[str, int]:
        """today 是 YYYY-MM-DD（本地日期）。updated_today 不含当天新建的条目。"""
        total = int(self.db.scalar("SELECT COUNT(*) FROM kb_articles WHERE scope=?", (scope,), 0))
        new = int(self.db.scalar("SELECT COUNT(*) FROM kb_articles WHERE scope=? AND substr(created_at,1,10)=?",
                                 (scope, today), 0))
        upd = int(self.db.scalar("SELECT COUNT(*) FROM kb_articles WHERE scope=? AND substr(updated_at,1,10)=? "
                                 "AND substr(created_at,1,10)<>?", (scope, today, today), 0))
        return {"total": total, "updated_today": upd, "new_today": new}

    def kb_related(self, kb_id: str, limit: int = 5) -> list[dict[str, str]]:
        me = self.kb_get(kb_id)
        if me is None:
            return []
        mine = {k.lower() for k in me.get("keywords") or []} | {t.lower() for t in me.get("tags") or []}
        scored = []
        for r in self.db.query("SELECT id, title, category, keywords, tags FROM kb_articles WHERE scope=? AND id<>?",
                               (me["scope"], kb_id)):
            other = {k.lower() for k in jload(r["keywords"], [])} | {t.lower() for t in jload(r["tags"], [])}
            s = len(mine & other) + (1 if r["category"] == me.get("category") else 0)
            if s >= 2:
                scored.append((s, r["id"], r["title"]))
        scored.sort(key=lambda x: (-x[0], x[2]))
        return [{"id": i, "title": t} for _, i, t in scored[:limit]]

    def kb_clear(self, scope: str) -> int:
        with self.db.tx():
            self.db.execute("DELETE FROM kb_versions WHERE kb_id IN (SELECT id FROM kb_articles WHERE scope=?)", (scope,))
            return self.db.execute("DELETE FROM kb_articles WHERE scope=?", (scope,)).rowcount
