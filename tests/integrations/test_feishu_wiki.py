"""feishu_doc 的 wiki 模式（知识库树）、幂等重试、single 模式兼容，以及 feishu_app 的风向标链接。

用有状态的假 lark-cli（内存里的空间 / 节点 / 文档），不启动子进程。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from bureau.channels.feishu_app import FeishuAppChannel
from bureau.channels.feishu_doc import FeishuDocChannel, demote_headings, escape_lt, nest_section
from bureau.contracts import ArticleBrief, ResourceBrief
from bureau.integrations.lark_cli import LarkCli, LarkCliError

from .helpers import TZ8, FakeLark, channel_ctx, lark_error, make_report, run

DOMAIN = "https://acme.feishu.cn"


def _opt(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args else None


class WikiFake:
    """假 lark-cli：维护空间、节点、文档；可以让指定标题的创建超时（可选"其实已建好"）或直接失败。"""

    def __init__(self, spaces: list[dict] | None = None) -> None:
        self.spaces = list(spaces or [])
        self.nodes: list[dict] = []
        self.docs: dict[str, dict] = {}
        self.calls: list[dict] = []
        self.n = 0
        self.timeout_titles: dict[str, bool] = {}      # 标题 -> 超时时是否其实已建好
        self.fail_titles: dict[str, tuple] = {}        # 标题 -> lark_error(...) 三元组
        self.fail_update: tuple | None = None

    def _id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:06d}AbCd"

    def _node(self, space_id, parent, title, obj=None):
        node = {"space_id": space_id, "node_token": self._id("wikcn"), "obj_token": obj or self._id("doxcn"),
                "obj_type": "docx", "parent_node_token": parent or "", "title": title, "node_type": "origin"}
        self.nodes.append(node)
        return node

    @staticmethod
    def ok(data):
        return 0, json.dumps({"ok": True, "identity": "user", "data": data}, ensure_ascii=False), ""

    async def __call__(self, argv, timeout, cwd, env):
        args = list(argv[1:])
        files = {}
        if cwd:
            files = {p.name: p.read_text("utf-8") for p in Path(cwd).glob("*.md")}
            imgs = sorted(str(p.relative_to(cwd)).replace("\\", "/") for p in Path(cwd).rglob("*.png"))
        else:
            imgs = []
        self.calls.append({"args": args, "cwd": cwd, "files": files, "images": imgs})
        cmd = tuple(args[:2])
        if cmd == ("wiki", "+space-list"):
            return self.ok({"spaces": self.spaces, "has_more": False, "page_token": ""})
        if cmd == ("wiki", "+space-create"):
            sp = {"space_id": "7160000000000000001", "name": _opt(args, "--name"), "space_type": "team"}
            self.spaces.append(sp)
            return self.ok(sp)
        if cmd == ("wiki", "+node-list"):
            sid, parent = _opt(args, "--space-id"), _opt(args, "--parent-node-token") or ""
            return self.ok({"nodes": [n for n in self.nodes if n["space_id"] == sid
                                      and n["parent_node_token"] == parent], "has_more": False})
        if cmd == ("wiki", "+node-create"):
            title = _opt(args, "--title")
            if title in self.fail_titles:
                return self.fail_titles[title]
            node = self._node(_opt(args, "--space-id"), _opt(args, "--parent-node-token"), title)
            return self.ok({"resolved_space_id": node["space_id"], "node_token": node["node_token"],
                            "obj_token": node["obj_token"], "obj_type": "docx", "title": title})
        if cmd == ("wiki", "+node-get"):
            tok = _opt(args, "--node-token")
            node = next((n for n in self.nodes if tok in (n["node_token"], n["obj_token"])), None)
            if node is None:
                return lark_error("api", "node not found", code=131005)
            return self.ok(dict(node))
        if cmd == ("docs", "+create"):
            title, parent = _opt(args, "--title"), _opt(args, "--parent-token")
            if title in self.fail_titles:
                return self.fail_titles[title]
            if title in self.timeout_titles:
                if self.timeout_titles[title]:
                    self._make_doc(parent, title, files.get(_opt(args, "--content")[1:], ""))
                raise LarkCliError("lark-cli 执行超时（120 秒）", kind="timeout", retryable=True)
            doc = self._make_doc(parent, title, files.get(_opt(args, "--content")[1:], ""))
            return self.ok({"document": {"document_id": doc["id"], "revision_id": 1,
                                         "url": f"{DOMAIN}/docx/{doc['id']}"}, "warnings": [], "tips": ""})
        if cmd == ("docs", "+update"):
            if self.fail_update and _opt(args, "--command") == self.fail_update[0]:
                return self.fail_update[1]
            doc = self.docs[_opt(args, "--doc")]
            doc.setdefault("updates", []).append((_opt(args, "--command"), files.get(_opt(args, "--content")[1:])))
            return self.ok({"document": {"document_id": doc["id"], "revision_id": 2}, "warnings": []})
        return 1, "", "unknown command"

    def _make_doc(self, parent, title, content):
        parent_node = next(n for n in self.nodes if n["node_token"] == parent)
        node = self._node(parent_node["space_id"], parent, title)
        doc = {"id": node["obj_token"], "title": title, "content": content, "node": node}
        self.docs[doc["id"]] = doc
        return doc

    def cmds(self) -> list[str]:
        return [" ".join(c["args"][:2]) for c in self.calls]

    def creates(self) -> list[str]:
        return [_opt(c["args"], "--title") or _opt(c["args"], "--name") for c in self.calls
                if tuple(c["args"][:2]) in (("docs", "+create"), ("wiki", "+node-create"), ("wiki", "+space-create"))]


def wiki_channel(tmp_path, fake, settings=None, channel_id="ch-wiki"):
    ch = FeishuDocChannel(channel_ctx(tmp_path, settings if settings is not None else {"identity": "user"},
                                      channel_id=channel_id))
    ch.cli = LarkCli(path="C:/fake/lark-cli.exe", runner=fake)
    ch.retry_base_delay, ch.write_interval = 0, 0
    return ch


def v2_report(n=3, *, report_id="r-20261030", assets_dir=None, images=None, **kw):
    arts = [ArticleBrief(id=f"a{i}", seq=i, title=f"专题标题{i}", hook=f"一句话{i}", category="03 AI 创作实战",
                         body_md=f"# {i:02d}-专题标题{i}\n> 分类：x\n**一句话**：钩子\n## 关键做法\n1. 步骤 <b>不是标签</b>\n"
                                 f"```\n提示词 <原文> 不转义\n```",
                         risk_flags=["平台规则"] if i == 2 else [], image_paths=(images or []) if i == 1 else [])
            for i in range(1, n + 1)]
    res = [ResourceBrief(kind="github", title="NapNeko/NapCatQQ", url="https://github.com/NapNeko/NapCatQQ",
                         meta={"stars": 11968, "language": "TypeScript"}, shared_by="青岚", group_name="水彩手绘研习社",
                         sent_at=datetime(2026, 10, 29, 9, 50, tzinfo=TZ8)),
           ResourceBrief(kind="netdisk", title="素材包", url="https://pan.quark.cn/s/abc", code="Ab12",
                         meta={"provider": "夸克网盘"})]
    base = dict(report_id=report_id, date_label="2026-10-30（周五）", title="情报局 · 每日风向标 | 2026-10-30（周五）",
                articles=arts, resources=res, assets_dir=assets_dir,
                sections={"overview": "# 今日总览\n一句话总结：今天很热闹。", "briefs": "- 快讯一\n- 快讯二"})
    base.update(kw)
    return make_report(**base)


# ---------------------------------------------------------------- wiki 主流程

def test_wiki_full_sequence_creates_space_tree_and_links(tmp_path):
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake)
    assert ch.mode == "wiki"
    res = run(ch.send(v2_report()))
    assert res.ok, res.detail
    assert fake.cmds() == ["wiki +space-list", "wiki +space-create", "wiki +node-list", "wiki +node-create",
                           "wiki +node-list", "docs +create", "wiki +node-get",
                           "docs +create", "docs +create", "docs +create", "docs +update"]
    assert fake.creates() == ["情报局知识库", "每日风向标", "2026-10-30（今日风向标）",
                              "01-专题标题1", "02-专题标题2", "03-专题标题3"]
    assert all("--as" in c["args"] and _opt(c["args"], "--as") == "user" for c in fake.calls)
    day_node = next(n for n in fake.nodes if n["title"] == "2026-10-30（今日风向标）")
    root = next(n for n in fake.nodes if n["title"] == "每日风向标")
    assert day_node["parent_node_token"] == root["node_token"]
    arts = [n for n in fake.nodes if n["title"].startswith("0")]
    assert {n["parent_node_token"] for n in arts} == {day_node["node_token"]}
    assert res.url == f"{DOMAIN}/wiki/{day_node['node_token']}" and res.external_id == res.url
    assert "专题 3 篇" in res.detail and res.parts == 4
    # 总览先写初稿（无链接），最后用带专题链接的终稿覆盖
    day_doc = fake.docs[day_node["obj_token"]]
    assert "文档生成中" in day_doc["content"]
    (cmd, final), = day_doc["updates"]
    assert cmd == "overwrite" and final.startswith("<title>2026-10-30（今日风向标）</title>")
    for n in arts:
        assert f"[{n['title']}]({DOMAIN}/docx/{n['obj_token']})" in final
    assert final.count("今日总览") == 1 and "## 今日总览\n\n一句话总结" in final   # 板块自带的同名标题不重复
    assert "| 💾" not in final and "Ab12" in final and "⭐ 11968" in final and "快讯二" in final
    assert "⚠️ 平台规则" in final
    # 专题正文：去掉重复的一级标题；正文里的 < 转义，代码块里的不动；参数只用 cwd 下的相对文件
    a1 = fake.docs[arts[0]["obj_token"]]["content"]
    assert not a1.startswith("# ") and "\\<b>不是标签" in a1 and "提示词 <原文> 不转义" in a1
    for c in fake.calls:
        content = _opt(c["args"], "--content")
        assert content is None or (content.startswith("@") and "/" not in content and ":" not in content)
    state = json.loads((tmp_path / "cache" / "feishu_wiki.json").read_text("utf-8"))["ch-wiki"]
    assert state["space_id"] == "7160000000000000001" and state["space_source"] == "created"
    assert state["domain"] == DOMAIN and state["reports"]["r-20261030"]["day"]["status"] == "done"
    assert not list((tmp_path / "tmp").iterdir())                         # 临时目录已清理


def test_wiki_second_send_is_noop(tmp_path):
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake)
    first = run(ch.send(v2_report()))
    n = len(fake.calls)
    second = run(ch.send(v2_report()))
    assert second.ok and second.url == first.url and len(fake.calls) == n    # 已全部完成：不再调用 lark-cli


def test_wiki_retry_only_fills_missing_parts_without_duplicates(tmp_path):
    fake = WikiFake()
    fake.timeout_titles["02-专题标题2"] = True                               # 超时，但其实已经建好
    fake.fail_titles["03-专题标题3"] = lark_error("api", "server busy", code=1500)
    ch = wiki_channel(tmp_path, fake)
    res = run(ch.send(v2_report()))
    assert not res.ok and res.retryable and res.url and "完成 1/3" in res.detail
    assert "结果不明" in res.detail and "server busy" in res.detail
    day_node = next(n for n in fake.nodes if n["title"] == "2026-10-30（今日风向标）")
    final = fake.docs[day_node["obj_token"]]["updates"][-1][1]
    assert "01-专题标题1](" in final and "02-专题标题2（文档生成中）" in final   # 总览照样写，未完成的不带链接
    fake.timeout_titles.clear()
    fake.fail_titles.clear()
    before = len(fake.calls)
    res2 = run(ch.send(v2_report()))
    assert res2.ok and res2.url == res.url
    retry_creates = [_opt(c["args"], "--title") for c in fake.calls[before:] if c["args"][:2] == ["docs", "+create"]]
    assert retry_creates == ["03-专题标题3"]                                  # 02 按标题找回，01 和总览不重建
    titles = [n["title"] for n in fake.nodes]
    assert titles.count("02-专题标题2") == 1 and titles.count("2026-10-30（今日风向标）") == 1
    final2 = fake.docs[day_node["obj_token"]]["updates"][-1][1]
    assert all(f"0{i}-专题标题{i}](" in final2 for i in (1, 2, 3))


def test_wiki_day_timeout_then_retry_adopts_existing_page(tmp_path):
    fake = WikiFake()
    fake.timeout_titles["2026-10-30（今日风向标）"] = True
    ch = wiki_channel(tmp_path, fake)
    res = run(ch.send(v2_report(n=1)))
    assert not res.ok and res.retryable and "结果不明" in res.detail
    fake.timeout_titles.clear()
    assert run(ch.send(v2_report(n=1))).ok
    assert [n["title"] for n in fake.nodes].count("2026-10-30（今日风向标）") == 1


def test_wiki_fatal_scope_error_stops_early(tmp_path):
    fake = WikiFake()
    fake.fail_titles["01-专题标题1"] = lark_error("authorization", "denied", subtype="missing_scope",
                                                 missing_scopes=["docx:document:create"])
    ch = wiki_channel(tmp_path, fake)
    res = run(ch.send(v2_report()))
    assert not res.ok and "docx:document:create" in res.detail
    assert [t for t in fake.creates() if t.startswith("0")] == ["01-专题标题1"]   # 权限问题不再逐篇重试


def test_wiki_reuses_existing_space_and_root(tmp_path):
    fake = WikiFake(spaces=[{"space_id": "7000000000000000009", "name": "情报局知识库"}])
    root = fake._node("7000000000000000009", "", "每日风向标")
    ch = wiki_channel(tmp_path, fake)
    assert run(ch.send(v2_report(n=1))).ok
    assert "情报局知识库" not in fake.creates() and "每日风向标" not in fake.creates()
    day = next(n for n in fake.nodes if n["title"].startswith("2026-10-30"))
    assert day["parent_node_token"] == root["node_token"] and day["space_id"] == "7000000000000000009"


def test_wiki_same_date_other_report_gets_version_suffix(tmp_path):
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake)
    assert run(ch.send(v2_report(n=1))).ok
    assert run(ch.send(v2_report(n=1, report_id="r-20261030-b"))).ok
    days = [n["title"] for n in fake.nodes if n["title"].startswith("2026-10-30")]
    assert days == ["2026-10-30（今日风向标）", "2026-10-30（今日风向标）（第 2 版）"]


def test_wiki_explicit_space_and_parent_node(tmp_path):
    fake = WikiFake()
    parent = fake._node("7111111111111111111", "", "我的每日风向标")
    ch = wiki_channel(tmp_path, fake, {"identity": "user", "parent_node": f"{DOMAIN}/wiki/{parent['node_token']}",
                                       "base_url": "https://my.feishu.cn"})
    res = run(ch.send(v2_report(n=1)))
    assert res.ok and res.url.startswith("https://my.feishu.cn/wiki/")
    assert "wiki +space-list" not in fake.cmds() and fake.creates()[0] == "2026-10-30（今日风向标）"
    assert _opt(fake.calls[0]["args"], "--node-token") == parent["node_token"]


def test_wiki_bot_identity_cannot_create_space(tmp_path):
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake, {"identity": "bot"})
    res = run(ch.send(v2_report(n=1)))
    assert not res.ok and not res.retryable and "知识空间 ID" in res.detail and fake.creates() == []
    bad = wiki_channel(tmp_path, fake, {"identity": "bot", "space_id": "my_library"})
    assert "my_library" in run(bad.send(v2_report(n=1))).detail
    assert "纯数字" in run(wiki_channel(tmp_path, fake, {"space_id": "abc"}).send(v2_report())).detail


def test_wiki_images_inserted_and_fallback_note(tmp_path):
    assets = tmp_path / "r_assets"
    assets.mkdir()
    Image.new("RGB", (20, 10), "blue").save(assets / "p1.png")
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake)
    res = run(ch.send(v2_report(n=1, assets_dir=str(assets), images=["p1.png", "../escape.png", "missing.png"])))
    assert res.ok and "插入图片 1 张" in res.detail
    append = next(c for c in fake.calls if _opt(c["args"], "--command") == "append")
    assert append["files"]["img01.md"].startswith("## 图片") and "![图 1](@./img01/01.png)" in append["files"]["img01.md"]
    assert append["images"] == ["img01/01.png"]                                    # 图片拷进 cwd，路径穿越的被忽略
    fake2 = WikiFake()
    fake2.fail_update = ("append", lark_error("api", "upload failed", code=1770001))
    ch2 = wiki_channel(tmp_path / "b", fake2)
    res2 = run(ch2.send(v2_report(n=1, assets_dir=str(assets), images=["p1.png"])))
    assert res2.ok                                                                 # 图片失败不影响投递结果
    appends = [c for c in fake2.calls if _opt(c["args"], "--command") == "append"]
    assert len(appends) == 2 and "图片见工作台" in appends[1]["files"]["note01.md"]


def test_wiki_works_with_v1_payload_and_test_message(tmp_path):
    fake = WikiFake()
    ch = wiki_channel(tmp_path, fake)
    res = run(ch.send(make_report()))                                               # 没有 articles / sections
    assert res.ok and res.url
    day = next(d for d in fake.docs.values() if d["title"].startswith("2026-10-28"))
    assert "正文……" in day["content"] and "updates" not in day      # 没有专题时初稿即终稿，不再覆盖
    t = run(ch.test())
    assert t.ok and any(n["title"].startswith("通道测试 ") for n in fake.nodes)


# ---------------------------------------------------------------- single 模式与配置

def test_single_mode_keeps_v1_behaviour_and_returns_url(tmp_path):
    data = {"document": {"document_id": "doxcn1", "url": "https://x.feishu.cn/docx/doxcn1"}, "warnings": [], "tips": ""}
    fake = FakeLark([(("docs", "+create"), data)])
    ch = FeishuDocChannel(channel_ctx(tmp_path, {"mode": "single", "identity": "user"}))
    ch.cli, ch.retry_base_delay = LarkCli(path="C:/fake/lark-cli.exe", runner=fake), 0
    res = run(ch.send(make_report()))
    assert res.ok and res.url == "https://x.feishu.cn/docx/doxcn1" and res.external_id == res.url
    assert fake.calls[0]["args"][:2] == ["docs", "+create"] and "--parent-token" not in fake.calls[0]["args"]
    again = run(ch.send(make_report()))
    assert again.ok and again.url == res.url and len(fake.calls) == 1


def test_mode_defaults():
    def mode(settings):
        return FeishuDocChannel(channel_ctx(Path("."), settings)).mode
    assert mode({}) == "wiki" and mode({"identity": "bot"}) == "wiki"
    assert mode({"parent_token": "wikcnX"}) == "single" and mode({"parent_position": "my_library"}) == "single"
    assert mode({"mode": "wiki", "parent_token": "wikcnX"}) == "wiki"
    keys = [f.key for f in FeishuDocChannel.config_schema()]
    assert keys[:4] == ["mode", "identity", "space_id", "parent_node"]


def test_markdown_helpers():
    assert escape_lt("a <b> c `x<y>` d\n```\n<raw>\n```\n\\<ok") == "a \\<b> c `x<y>` d\n```\n<raw>\n```\n\\<ok"
    assert demote_headings("# A\n```\n# not\n```\n###### F") == "## A\n```\n# not\n```\n###### F"
    assert nest_section("# 资源库\n## GitHub\n表", "资源库") == "### GitHub\n表"
    assert nest_section("### 已经够深\n正文", "资源库") == "### 已经够深\n正文"
    assert nest_section("没有标题", "快讯") == "没有标题"


# ---------------------------------------------------------------- feishu_app：风向标直达链接

def test_feishu_app_appends_doc_link_once(tmp_path):
    ok = {"message_id": "om_x", "chat_id": "oc_x", "create_time": "1"}
    fake = FakeLark([(("im", "+messages-send"), ok)])
    ch = FeishuAppChannel(channel_ctx(tmp_path, {"target_type": "user_id", "target_id": "ou_me"}))
    ch.cli, ch.retry_base_delay, ch.part_interval = LarkCli(path="C:/fake/lark-cli.exe", runner=fake), 0, 0
    url = "https://acme.feishu.cn/wiki/wikcnDay"
    assert run(ch.send(make_report(doc_links={"feishu_doc": url}))).ok
    md = fake.calls[0]["files"]["report.md"]
    assert f"[查看今日风向标]({url})" in md and md.count(url) == 1
    fake2 = FakeLark([(("im", "+messages-send"), ok)])
    ch.cli = LarkCli(path="C:/fake/lark-cli.exe", runner=fake2)
    assert run(ch.send(make_report(report_id="r2", summary_md=f"已更新 👉 {url}", doc_links={"feishu_doc": url}))).ok
    assert fake2.calls[0]["files"]["report.md"].count(url) == 1                     # 正文里已有链接就不再追加
    fake3 = FakeLark([(("im", "+messages-send"), ok)])
    ch.cli = LarkCli(path="C:/fake/lark-cli.exe", runner=fake3)
    assert run(ch.send(make_report(report_id="r3", doc_links={"feishu_doc": "javascript:alert(1)"}))).ok
    assert "javascript" not in fake3.calls[0]["files"]["report.md"]
