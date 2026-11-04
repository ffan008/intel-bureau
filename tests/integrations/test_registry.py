"""注册表里 B 负责的每个键都能加载，类名、kind/key 与注册表一致，表单字段中文、密钥字段为 secret。"""

from __future__ import annotations

import re

import pytest

from bureau.channels import CHANNEL_REGISTRY, load_channel_class
from bureau.collectors import COLLECTOR_REGISTRY, load_collector_class
from bureau.channels.base import split_text
from bureau.integrations.push_common import markdown_to_html

CJK = re.compile(r"[一-鿿]")
PROPER_NOUNS = {"Token", "API Token", "SPT", "SendKey", "appToken", "QQ"}       # 产品里的专有名词保持原样


def _label_ok(label: str) -> bool:
    return bool(CJK.search(label)) or label in PROPER_NOUNS
SECRET_KEYS = {"token", "report_secret", "webhook_url", "sign_secret", "webhook", "sendkey", "spt", "app_token", "password"}
B_COLLECTORS = [k for k in COLLECTOR_REGISTRY if not k.startswith("demo.")]
B_CHANNELS = [k for k in CHANNEL_REGISTRY if k != "local_archive"]


@pytest.mark.parametrize("key", B_COLLECTORS)
def test_collector_registry(key):
    cls = load_collector_class(key)
    assert cls.__name__ == COLLECTOR_REGISTRY[key].split(":")[1]
    if "file_import" not in key:
        assert cls.key == key
    assert cls.label
    for f in cls.config_schema():
        assert _label_ok(f.label), f.key
        if f.key in SECRET_KEYS:
            assert f.type == "secret", f.key


@pytest.mark.parametrize("kind", B_CHANNELS)
def test_channel_registry(kind):
    cls = load_channel_class(kind)
    assert cls.__name__ == CHANNEL_REGISTRY[kind].split(":")[1] and cls.kind == kind
    assert _label_ok(cls.platform_label)
    for f in cls.config_schema():
        assert _label_ok(f.label), f.key
        if f.help:
            assert CJK.search(f.help), f.key
        if f.key in SECRET_KEYS:
            assert f.type == "secret", f.key


def test_markdown_to_html_escapes_raw_html():
    html = markdown_to_html("<script>alert(1)</script>\n[x](javascript:alert(1)) [ok](https://e.com/a?b=1&c=2)")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'href="javascript' not in html and 'href="https://e.com/a?b=1&amp;c=2"' in html


def test_split_text_bytes_respects_limit():
    parts = split_text("中文" * 3000, 4096, measure="bytes")
    assert all(len(p.encode("utf-8")) <= 4096 for p in parts) and "".join(parts) == "中文" * 3000