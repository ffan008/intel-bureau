"""按采集器写在 ``attachment["extra"]["fetch"]`` 里的描述取回图片 / 文件，存到 dest_dir。

文件名为 ``sha256 前 16 位 + 扩展名``（扩展名按文件内容判断，其次按原文件名）。同一内容只存一份。

fetch 描述（B2 定义，A2 原样传回；字段缺失时尽力而为）：

- ``{"type": "local", "path": "<绝对路径，或相对项目根目录>"}``（演示数据用）
- ``{"type": "url", "url": "https://..."}``：公网直链，走 SSRF 防护
- ``{"type": "wda", "account", "username", "kind": "image|video|file", "md5", "file_id", "server_id",
  "title", "file_size", "create_time"}``：WeChatDataAnalysis 本地 API。
  图片 ``GET /api/chat/media/image?account=&username=&md5=&file_id=&server_id=``；
  视频 ``GET /api/chat/media/video?account=&username=&md5=&file_id=``；
  文件 WDA 没有下载接口：先 ``GET /api/chat/accounts`` 取该账号的 ``wxidDir``，再只读访问
  ``<wxidDir>/msg/file/<YYYY-MM>/<文件名>``（微信 4.x 收到的文件以明文保存在这里），按大小 / MD5 核对。
- ``{"type": "onebot", "action": "get_image|get_file", "file", "file_id", "group_id", "url", "busid"}``：
  NapCat（OneBot 11）。``get_image`` / ``get_file`` 的参数是 ``file``（或 ``file_id``），返回
  ``{file: 本地路径, url, file_size, file_name, base64?}``；群文件还可以 ``get_group_file_url``
  （``group_id`` + ``file_id``）拿下载链接。
- ``{"type": "lark", "message_id": "om_…", "file_key": "img_…|file_…", "resource_type": "image|file",
  "identity": "user"}``：``lark-cli im +messages-resources-download --as user --message-id … --file-key …
  --type … --output <相对路径>``，返回 ``data.saved_path / size_bytes``。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from bureau.integrations.lark_cli import LarkCli, LarkCliError, Runner
from bureau.integrations.netsafe import FetchError, Resolver, UnsafeURLError, safe_get
from bureau.integrations.onebot import DEFAULT_BASE_URL as ONEBOT_URL, OneBotClient, OneBotError
from bureau.integrations.wda_auth import discover_token, is_loopback_url
from bureau.media.models import MediaResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WDA_URL = "http://127.0.0.1:10392"
DEFAULT_MAX_MB = 20
_ID = re.compile(r"^[A-Za-z0-9_.:@=+/-]{1,300}$")
_LARK_MSG = re.compile(r"^om_[A-Za-z0-9_-]{4,120}$")
_LARK_KEY = re.compile(r"^[A-Za-z0-9_-]{4,200}$")


class _Fail(Exception):
    """取回失败，message 为中文。"""


# ---------------------------------------------------------------- 内容识别

def sniff_type(data: bytes, filename: str | None = None) -> tuple[str, str]:
    """按文件头判断 (mime, 扩展名)。"""
    h = data[:16]
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if h.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if h[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if h[:2] == b"BM":
        return "image/bmp", ".bmp"
    if h.startswith(b"%PDF"):
        return "application/pdf", ".pdf"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"heim"):
            return "image/heic", ".heic"
        return "video/mp4", ".mp4"
    if h.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm", ".webm"
    if h.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            names = set()
        if "word/document.xml" in names:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
        if "xl/workbook.xml" in names:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"
        if "ppt/presentation.xml" in names:
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
    ext = Path(filename or "").suffix.lower()
    if ext and re.fullmatch(r"\.[a-z0-9]{1,8}", ext):
        return mimetypes.types_map.get(ext) or mimetypes.guess_type("x" + ext)[0] or "application/octet-stream", ext
    if h.startswith(b"PK\x03\x04"):
        return "application/zip", ".zip"
    try:
        data[:4096].decode("utf-8")
        return "text/plain", ".txt"
    except UnicodeDecodeError:
        return "application/octet-stream", ".bin"


def _image_size(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except Exception:  # noqa: BLE001 — 不是 Pillow 能读的图片
        return None, None


def _store(data: bytes, dest_dir: Path, kind: str, filename: str | None, max_bytes: int) -> MediaResult:
    if not data:
        raise _Fail("取回的文件是空的")
    if len(data) > max_bytes:
        raise _Fail(f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
    digest = hashlib.sha256(data).hexdigest()
    mime, ext = sniff_type(data, filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{digest[:16]}{ext}"
    if not target.is_file() or target.stat().st_size != len(data):
        fd, tmp = tempfile.mkstemp(dir=dest_dir, prefix=".m-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    width = height = None
    if mime.startswith("image/"):
        width, height = _image_size(data)
    return MediaResult(ok=True, kind=kind, path=str(target), filename=filename or target.name, mime=mime,  # type: ignore[arg-type]
                       size=len(data), width=width, height=height, sha256=digest)


def _read_file(path: Path, max_bytes: int) -> bytes:
    try:
        if not path.is_file():
            raise _Fail("文件不存在")
        size = path.stat().st_size
    except OSError:
        raise _Fail("无法访问文件") from None
    if size > max_bytes:
        raise _Fail(f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
    try:
        return path.read_bytes()
    except OSError:
        raise _Fail("读取文件失败") from None


# ---------------------------------------------------------------- 各平台

def _section(cfg: dict, *keys: str) -> dict:
    cur: Any = cfg or {}
    for k in keys:
        cur = cur.get(k) if isinstance(cur, dict) else None
    return cur if isinstance(cur, dict) else {}


async def _local(spec: dict, max_bytes: int) -> tuple[bytes, str | None]:
    raw = str(spec.get("path") or "").strip()
    if not raw:
        raise _Fail("没有提供本地文件路径")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return await asyncio.to_thread(_read_file, p, max_bytes), p.name


async def _url(url: str, max_bytes: int, transport, resolver, *, referer: str | None = None) -> bytes:
    headers = {"Accept": "*/*"}
    if referer and referer.lower().startswith(("http://", "https://")):
        headers["Referer"] = referer
    try:
        resp = await safe_get(url, transport=transport, resolver=resolver, timeout=30.0, max_bytes=max_bytes,
                              headers=headers, oversize="error")
    except UnsafeURLError as exc:
        raise _Fail(str(exc)) from None
    except FetchError as exc:
        raise _Fail(exc.message) from None
    if resp.status >= 400:
        raise _Fail(f"下载失败（HTTP {resp.status}）")
    return resp.content


def _wda_base(app_cfg: dict) -> str:
    return str(_section(app_cfg, "sources", "wechat", "wda").get("base_url") or WDA_URL).rstrip("/")


def _wda_auth(app_cfg: dict, secrets: dict, base: str) -> dict[str, str]:
    """2.x 桌面版的媒体接口同样要 Token：设置里填了就用，否则自动读本机应用（只对 127.0.0.1 发）。"""
    token = str(_section(secrets, "sources", "wechat", "wda").get("token") or "").strip()
    if not token:
        if not is_loopback_url(base):
            return {}
        token = discover_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _wda_get(base: str, path: str, params: dict, transport, max_bytes: int,
                   timeout: float = 60.0, headers: dict[str, str] | None = None) -> tuple[int, str, bytes]:
    """GET WDA 本地接口，返回 (状态码, content-type, 已解压的正文)。"""
    clean = {k: v for k, v in params.items() if v not in (None, "", 0)}
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout, trust_env=False) as client:
            async with client.stream("GET", f"{base}{path}", params=clean, headers=headers or {}) as resp:
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    if len(buf) > max_bytes:
                        raise _Fail(f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                return resp.status_code, (resp.headers.get("content-type") or "").lower(), bytes(buf)
    except httpx.ConnectError:
        raise _Fail("连不上 WeChatDataAnalysis，请确认它正在运行") from None
    except httpx.TimeoutException:
        raise _Fail("WeChatDataAnalysis 响应超时") from None
    except httpx.HTTPError as exc:
        raise _Fail(f"访问 WeChatDataAnalysis 出错（{type(exc).__name__}）") from None


def _wda_file_lookup(wxid_dir: str, title: str, create_time: Any, file_size: Any, md5: str) -> Path:
    name = str(title or "").strip()
    if not name or Path(name).name != name or name in (".", "..") or any(c in name for c in '\\/:*?"<>|'):
        raise _Fail("文件名不合法，无法在微信目录里定位")
    root = Path(wxid_dir) / "msg" / "file"
    if not root.is_dir():
        raise _Fail("找不到微信的文件目录（msg/file）")
    stem, ext = os.path.splitext(name)
    months: list[Path] = []
    try:
        ts = float(create_time)
        months.append(root / datetime.fromtimestamp(ts if ts < 1e12 else ts / 1000).strftime("%Y-%m"))
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    months += sorted((d for d in root.iterdir() if d.is_dir() and d not in months), reverse=True)
    want_size = int(file_size) if str(file_size or "").isdigit() else None
    want_md5 = str(md5 or "").lower() if re.fullmatch(r"[0-9a-fA-F]{32}", str(md5 or "")) else ""
    pattern = re.compile(re.escape(stem) + r"(?:\(\d+\))?" + re.escape(ext) + r"$")
    root_resolved = root.resolve()
    for month in months:
        try:
            cands = [p for p in month.iterdir() if p.is_file() and pattern.fullmatch(p.name)]
        except OSError:
            continue
        for p in sorted(cands, key=lambda x: len(x.name)):
            try:
                if root_resolved not in p.resolve().parents:
                    continue
                if want_size is not None and p.stat().st_size != want_size:
                    continue
                if want_md5 and hashlib.md5(p.read_bytes()).hexdigest() != want_md5:  # noqa: S324 — 只用于核对
                    continue
            except OSError:
                continue
            return p
    raise _Fail("在微信的文件目录里没有找到这个文件（可能还没下载到本机）")


async def _wda(spec: dict, app_cfg: dict, secrets: dict, max_bytes: int,
               transport) -> tuple[bytes, str | None]:
    base = _wda_base(app_cfg)
    headers = _wda_auth(app_cfg, secrets, base)
    kind = str(spec.get("kind") or "image")
    common = {"account": spec.get("account"), "username": spec.get("username")}
    for k in ("account", "username", "md5", "file_id"):
        v = str(spec.get(k) or "")
        if v and not _ID.match(v):
            raise _Fail(f"fetch 描述里的 {k} 不合法")
    if kind in ("image", "video"):
        if not (spec.get("md5") or spec.get("file_id") or spec.get("server_id")):
            raise _Fail("缺少 md5 / file_id / server_id，无法取回")
        params = common | {"md5": spec.get("md5"), "file_id": spec.get("file_id")}
        if kind == "image":
            params["server_id"] = spec.get("server_id")
        status, ctype, body = await _wda_get(base, f"/api/chat/media/{kind}", params, transport, max_bytes,
                                             headers=headers)
        if status == 401:
            raise _Fail("WeChatDataAnalysis 要求有效的 API Token（HTTP 401）：在采集器设置里填写 Token")
        if status != 200 or ctype.startswith(("application/json", "text/")):
            raise _Fail(f"WeChatDataAnalysis 没有返回{('图片' if kind == 'image' else '视频')}（HTTP {status}）")
        return body, spec.get("title")
    if kind == "file":
        _status, _ctype, body = await _wda_get(base, "/api/chat/accounts", {}, transport, 4 * 1024 * 1024,
                                               timeout=15.0, headers=headers)
        if _status == 401:
            raise _Fail("WeChatDataAnalysis 要求有效的 API Token（HTTP 401）：在采集器设置里填写 Token")
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            raise _Fail("WeChatDataAnalysis 返回的账号信息不是 JSON") from None
        if not isinstance(data, dict):
            raise _Fail("WeChatDataAnalysis 返回的账号信息格式不正确")
        account = str(spec.get("account") or data.get("default_switchable_account") or data.get("default_account") or "")
        info = next((i for i in data.get("accountInfos") or [] if isinstance(i, dict)
                     and str(i.get("account") or "") == account), {})
        wxid_dir = str(info.get("wxidDir") or "").strip()
        if not wxid_dir:
            raise _Fail("WeChatDataAnalysis 没有提供该账号的微信数据目录（wxidDir），无法取回文件")
        p = await asyncio.to_thread(_wda_file_lookup, wxid_dir, str(spec.get("title") or ""),
                                    spec.get("create_time"), spec.get("file_size"), str(spec.get("md5") or ""))
        return await asyncio.to_thread(_read_file, p, max_bytes), p.name
    raise _Fail(f"不支持的 WDA 资源类型：{kind[:20]}")


async def _onebot(spec: dict, app_cfg: dict, secrets: dict, max_bytes: int, transport,
                  resolver) -> tuple[bytes, str | None]:
    base = str(_section(app_cfg, "sources", "qq", "onebot").get("base_url") or ONEBOT_URL)
    token = str(_section(secrets, "sources", "qq", "onebot").get("token") or "") or None
    client = OneBotClient(base, token, transport=transport, timeout=60.0)
    action = str(spec.get("action") or "get_image")
    if action not in ("get_image", "get_file", "get_record"):
        raise _Fail("不支持的 OneBot 取回方式")
    ref = str(spec.get("file") or spec.get("file_id") or "")
    errors: list[str] = []
    name = str(spec.get("name") or "") or None
    if ref:
        try:
            data = await client.call(action, timeout=60.0, file=ref,
                                     **({"file_id": spec["file_id"]} if spec.get("file_id") else {}))
        except OneBotError as exc:
            errors.append(exc.message)
            data = None
        if isinstance(data, dict):
            name = str(data.get("file_name") or "") or name
            if data.get("base64"):
                try:
                    raw = base64.b64decode(str(data["base64"]), validate=False)
                    if len(raw) > max_bytes:
                        raise _Fail(f"文件超过大小上限（{max_bytes // (1024 * 1024)} MB）")
                    return raw, name
                except (ValueError, TypeError):
                    errors.append("NapCat 返回的 base64 无法解码")
            local = str(data.get("file") or "")
            if local and not local.lower().startswith(("http://", "https://")):
                try:
                    return await asyncio.to_thread(_read_file, Path(local), max_bytes), name or Path(local).name
                except _Fail as exc:
                    errors.append(f"NapCat 给出的本地文件不可读（{exc}）")
            url = str(data.get("url") or "")
            if url.lower().startswith(("http://", "https://")):
                try:
                    return await _url(url, max_bytes, transport, resolver), name
                except _Fail as exc:
                    errors.append(str(exc))
    if spec.get("group_id") and spec.get("file_id") and action == "get_file":
        try:
            data = await client.call("get_group_file_url", group_id=str(spec["group_id"]), file_id=str(spec["file_id"]),
                                     **({"busid": spec["busid"]} if spec.get("busid") else {}))
            url = str((data or {}).get("url") or "") if isinstance(data, dict) else ""
            if url.lower().startswith(("http://", "https://")):
                return await _url(url, max_bytes, transport, resolver), name
            errors.append("get_group_file_url 没有返回下载链接")
        except OneBotError as exc:
            errors.append(exc.message)
        except _Fail as exc:
            errors.append(str(exc))
    hint = str(spec.get("local_hint") or "")
    if hint and len(hint) > 2 and hint[1] == ":":
        try:
            return await asyncio.to_thread(_read_file, Path(hint), max_bytes), name or Path(hint).name
        except _Fail as exc:
            errors.append(f"NapCat 本机缓存文件不可读（{exc}）")
    url = str(spec.get("url") or "")
    if url.lower().startswith(("http://", "https://")):
        try:
            return await _url(url, max_bytes, transport, resolver), name
        except _Fail as exc:
            errors.append(str(exc))
    raise _Fail("；".join(dict.fromkeys(errors)) or "没有可用的取回方式")


async def _lark(spec: dict, app_cfg: dict, dest_dir: Path, max_bytes: int,
                runner: Runner | None) -> tuple[bytes, str | None]:
    mid, key = str(spec.get("message_id") or ""), str(spec.get("file_key") or "")
    if not _LARK_MSG.match(mid) or not _LARK_KEY.match(key):
        raise _Fail("fetch 描述里的 message_id 或 file_key 不合法")
    rtype = "image" if str(spec.get("resource_type") or "") == "image" else "file"
    identity = "bot" if str(spec.get("identity") or "user") == "bot" else "user"
    cfg = _section(app_cfg, "sources", "feishu", "lark_cli")
    if runner is not None:                     # 测试注入假 lark-cli
        cli = LarkCli(path="lark-cli", runner=runner, timeout=120.0)
    else:
        cli = LarkCli(cli_path=str(cfg.get("cli_path") or "") or None, timeout=120.0)
    if not cli.available:
        raise _Fail("没有找到 lark-cli")
    dest_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".lark-dl-", dir=dest_dir))
    try:
        try:
            data = await cli.run(["im", "+messages-resources-download", "--as", identity, "--message-id", mid,
                                  "--file-key", key, "--type", rtype, "--output", "resource", "--format", "json"],
                                 cwd=str(work), timeout=120.0, identity=identity)
        except LarkCliError as exc:
            raise _Fail(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None
        saved = str((data or {}).get("saved_path") or "") if isinstance(data, dict) else ""
        cands = []
        if saved:
            sp = Path(saved)
            cands.append(sp if sp.is_absolute() else work / sp)
        cands += sorted(work.glob("resource*"))
        work_resolved = work.resolve()
        for c in cands:
            try:
                if c.is_file() and (c.resolve() == work_resolved or work_resolved in c.resolve().parents):
                    return await asyncio.to_thread(_read_file, c, max_bytes), spec.get("name") or None
            except OSError:
                continue
        raise _Fail("lark-cli 显示下载成功，但没有找到下载的文件")
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- 入口

def _as_dict(attachment: Any) -> dict:
    if hasattr(attachment, "model_dump"):
        return attachment.model_dump()
    return dict(attachment) if isinstance(attachment, dict) else {}


async def fetch_media(app_cfg: dict, secrets: dict, platform: str, attachment: dict, dest_dir: Path, *,
                      transport: httpx.AsyncBaseTransport | None = None, resolver: Resolver | None = None,
                      lark_runner: Runner | None = None) -> MediaResult:
    """取回附件。app_cfg / secrets 为完整的 settings / secrets；transport、resolver、lark_runner 仅供测试注入。"""
    att = _as_dict(attachment)
    akind = str(att.get("kind") or "file")
    kind = akind if akind in ("image", "video") else "file"
    extra = att.get("extra") if isinstance(att.get("extra"), dict) else {}
    spec = extra.get("fetch") if isinstance(extra.get("fetch"), dict) else None
    if spec is None and str(att.get("url") or "").lower().startswith(("http://", "https://")):
        spec = {"type": "url", "url": att["url"]}
    if spec is None:
        return MediaResult(ok=False, kind=kind, filename=att.get("title"), error="附件没有可用的取回方式（缺少 extra.fetch）")  # type: ignore[arg-type]
    try:
        mb = float(_section(app_cfg, "media").get("max_file_mb") or DEFAULT_MAX_MB)
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_MB
    max_bytes = int(max(0.1, mb) * 1024 * 1024)
    dest = Path(dest_dir)
    title = str(att.get("title") or "") or None
    stype = str(spec.get("type") or "")
    try:
        if stype == "local":
            data, name = await _local(spec, max_bytes)
        elif stype == "url":
            data, name = await _url(str(spec.get("url") or ""), max_bytes, transport, resolver,
                                    referer=spec.get("referer")), None
        elif stype == "wda":
            data, name = await _wda(spec, app_cfg, secrets, max_bytes, transport)
        elif stype == "onebot":
            data, name = await _onebot(spec, app_cfg, secrets, max_bytes, transport, resolver)
        elif stype == "lark":
            data, name = await _lark(spec, app_cfg, dest, max_bytes, lark_runner)
        else:
            raise _Fail(f"不支持的取回类型：{stype[:20] or '空'}（平台 {platform}）")
        return await asyncio.to_thread(_store, data, dest, kind, title or name, max_bytes)
    except _Fail as exc:
        return MediaResult(ok=False, kind=kind, filename=title, error=str(exc))  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 — 约定不抛异常
        return MediaResult(ok=False, kind=kind, filename=title,  # type: ignore[arg-type]
                           error=f"取回附件时出现未预期的错误（{type(exc).__name__}）")
