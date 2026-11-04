"""compose 子步骤 1：媒体。下载被引用的图片和文件（B2 的 bureau.media.fetch_media），图片 OCR，文档解析出正文后提炼要点。

B2 模块不可用时：只列出被引用的媒体（文件名、出处、为什么有用），标「未取回」，不中断流水线。
OCR 选 llm（视觉模型）时需要云端同意，否则跳过 OCR 并在日志说明。违法高危话题的媒体不处理。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from bureau.core.textutil import truncate
from bureau.pipeline.b2 import media_api, scoped_secrets
from bureau.pipeline.models import RunContext
from bureau.pipeline.risk import is_illegal
from bureau.pipeline.score import report_day

FETCH_TIMEOUT = 90.0


def key_lines(text: str, n: int = 5, width: int = 60) -> list[str]:
    """提炼要点（抽取式，不改写）：取前几行有信息量的文字。"""
    out: list[str] = []
    for ln in re.split(r"[\r\n]+", text or ""):
        s = re.sub(r"\s+", " ", ln).strip(" ·•-—|#*")
        if len(s) >= 6 and s not in out:
            out.append(truncate(s, width))
        if len(out) >= n:
            break
    return out


def collect_refs(rc: RunContext) -> list[dict[str, Any]]:
    """被引用的媒体（按话题排名），每条消息只处理一次。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in sorted(rc.items, key=lambda x: x.rank):
        if is_illegal(it):
            continue
        for r in it.media_refs:
            if r["msg"] in seen:
                continue
            seen.add(r["msg"])
            out.append({"ref": r["msg"], "kind": r["kind"], "name": r.get("name") or "", "why": r.get("why") or "",
                        "sender": r["sender"], "group_name": r["group_name"], "group_key": r["group_key"],
                        "platform": r["platform"], "sent_at": r["sent_at"], "message_id": r["message_id"],
                        "attachment": r.get("attachment") or {}, "item_id": it.id, "article_seq": it.seq or None,
                        "ok": False, "path": None, "ocr_text": "", "summary": "", "points": [], "note": ""})
    return out


def demo_local(rc: RunContext, entries: list[dict[str, Any]]) -> int:
    """媒体模块不可用时的演示兜底：只认 data_dir/demo_media/ 下、extra.fetch.type=local 的演示素材，
    直接引用文件（不复制以外的处理，不做 OCR 和文档解析）。真实运行不走这里。"""
    root = rc.app.paths.demo_media.resolve()
    n = 0
    for e in entries:
        f = (e.get("attachment") or {}).get("extra", {}).get("fetch") or {}
        if f.get("type") != "local" or not f.get("path"):
            continue
        p = Path(str(f["path"])).resolve()
        if root not in p.parents or not p.is_file():
            continue
        e.update(ok=True, path=str(p), size=p.stat().st_size, name=e.get("name") or p.name,
                 note="演示素材（媒体模块不可用，未做 OCR / 文档解析）")
        n += 1
    return n


def _attach(rc: RunContext, entries: list[dict[str, Any]]) -> None:
    by_id = {it.id: it for it in rc.items}
    for e in entries:
        it = by_id.get(e["item_id"])
        if it is not None and e not in it.media:
            it.media.append(e)


async def run_media(rc: RunContext) -> dict[str, Any]:
    entries = collect_refs(rc)
    stats = {"refs": len(entries), "fetched": 0, "ocr": 0, "docs": 0, "failed": 0, "skipped": ""}
    rc.media = entries
    _attach(rc, entries)
    if not entries:
        return stats
    if not rc.cfg("media.enabled", True):
        stats["skipped"] = "media.enabled=false"
        for e in entries:
            e["note"] = "未取回（设置里关闭了媒体处理）"
        rc.log.info("WRITER", f"媒体处理已关闭：{len(entries)} 个被引用的图片 / 文件只列出处", "compose")
        return stats
    mod, why = media_api()
    if mod is None:
        stats["skipped"] = why
        local = demo_local(rc, entries) if rc.demo else 0
        for e in entries:
            e["note"] = e.get("note") or "未取回（媒体模块不可用）"
        stats["fetched"] = local
        rc.log.warn("WRITER", f"跳过媒体子步骤：{why}；{len(entries)} 个被引用的图片 / 文件只列出处"
                    + (f"（演示素材 {local} 个按本地路径直接引用，不做 OCR 和文档解析）" if local else ""), "compose")
        return stats
    max_img, max_file = int(rc.cfg("media.max_images", 40) or 0), int(rc.cfg("media.max_files", 15) or 0)
    max_bytes = int(float(rc.cfg("media.max_file_mb", 20) or 20) * 1024 * 1024)
    ocr_mode = str(rc.cfg("media.ocr", "windows") or "off")
    if ocr_mode == "llm" and not rc.cfg("privacy.cloud_llm_consent", False):
        rc.log.warn("WRITER", "OCR 选了 llm（视觉模型），但未同意使用云端模型：本次跳过 OCR", "compose")
        ocr_mode = "off"
    images = [e for e in entries if e["kind"] == "image"][:max_img]
    files = [e for e in entries if e["kind"] == "file"][:max_file]
    for e in entries:
        if e not in images and e not in files:
            e["note"] = "未取回（超过本次运行的数量上限）"
    dest = rc.app.paths.media_cache / report_day(rc)
    dest.mkdir(parents=True, exist_ok=True)
    app_cfg = rc.settings
    secrets = scoped_secrets(rc.app.config.secrets_tree(), "sources", "llm", "media")
    sem = asyncio.Semaphore(3)

    async def one(e: dict[str, Any]) -> None:
        async with sem:
            try:
                res = await asyncio.wait_for(mod.fetch_media(app_cfg, secrets, e["platform"], e["attachment"], dest),
                                             FETCH_TIMEOUT)
            except Exception as exc:                                 # noqa: BLE001
                e["note"] = f"取回失败：{exc or '超时'}"
                stats["failed"] += 1
                return
            if not getattr(res, "ok", False) or not getattr(res, "path", None):
                e["note"] = f"取回失败：{getattr(res, 'error', None) or '未知原因'}"
                stats["failed"] += 1
                return
            if res.size and res.size > max_bytes:
                e["note"] = f"文件超过 {max_bytes // 1024 // 1024} MB，未处理"
                stats["failed"] += 1
                return
            e.update(ok=True, path=str(res.path), mime=res.mime, size=res.size, width=res.width, height=res.height,
                     name=e["name"] or res.filename or Path(str(res.path)).name)
            stats["fetched"] += 1
            try:
                if e["kind"] == "image" and ocr_mode != "off":
                    text = await asyncio.wait_for(mod.ocr_image(Path(res.path), mode=ocr_mode, settings=app_cfg,
                                                                secrets=secrets), FETCH_TIMEOUT)
                    e["ocr_text"] = (text or "").strip()[:4000]
                    e["points"] = key_lines(e["ocr_text"], 4)
                    stats["ocr"] += bool(e["ocr_text"])
                elif e["kind"] == "file":
                    text = await asyncio.wait_for(mod.extract_document(Path(res.path), max_chars=20000), FETCH_TIMEOUT)
                    e["text"] = (text or "").strip()
                    e["points"] = key_lines(e["text"], 6)
                    e["summary"] = "；".join(e["points"][:3])
                    stats["docs"] += bool(e["text"])
                    if not e["text"]:
                        e["note"] = "没有读出正文（格式不支持或是扫描件）"
            except Exception as exc:                                 # noqa: BLE001
                e["note"] = f"解析失败：{exc or '超时'}"

    await asyncio.gather(*(one(e) for e in images + files))
    rc.log.info("WRITER", f"媒体：被引用 {stats['refs']} 个，取回 {stats['fetched']} 个，OCR {stats['ocr']} 张，"
                          f"解析文档 {stats['docs']} 个，失败 {stats['failed']} 个", "compose")
    return stats
