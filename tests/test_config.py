"""配置生成、深合并与密钥掩码。"""

from __future__ import annotations

import yaml

from bureau.core.config import ConfigManager, deep_merge
from bureau.core.security import is_masked, is_unchanged_secret, mask_secret, mask_tree, redact_text


def test_settings_generated_from_example(paths):
    assert not paths.settings.exists()
    cfg = ConfigManager(paths)
    assert paths.settings.exists()
    assert cfg.get("app.port") == 8765
    assert cfg.get("privacy.cloud_llm_consent") is False
    assert cfg.get("llm.provider") == "auto"


def test_secrets_created_with_random_token(paths):
    cfg = ConfigManager(paths)
    assert paths.secrets.exists()
    token = cfg.token
    assert len(token) >= 24
    data = yaml.safe_load(paths.secrets.read_text(encoding="utf-8"))
    assert data["app"]["token"] == token
    # 再次加载保持不变
    assert ConfigManager(paths).token == token


def test_token_differs_between_installs(tmp_path):
    from tests.conftest import make_paths

    a = ConfigManager(make_paths(tmp_path / "a")).token
    b = ConfigManager(make_paths(tmp_path / "b")).token
    assert a != b


def test_deep_merge_and_update(paths):
    assert deep_merge({"a": {"b": 1, "c": [1]}}, {"a": {"c": [2], "d": 3}}) == {"a": {"b": 1, "c": [2], "d": 3}}
    cfg = ConfigManager(paths)
    cfg.update_settings({"pipeline": {"top_n": 7}})
    assert cfg.get("pipeline.top_n") == 7
    assert cfg.get("pipeline.max_features") == 12         # 其它键保留（v2 默认 12 篇专题）
    assert cfg.get("pipeline.risk_policy") == "label" and cfg.get("pipeline.risk_penalty") == 0   # v2 默认
    assert ConfigManager(paths).get("pipeline.top_n") == 7  # 已写回文件


def test_new_example_keys_apply_to_existing_settings(paths):
    paths.settings.write_text("app:\n  port: 9000\n", encoding="utf-8")
    cfg = ConfigManager(paths)
    assert cfg.get("app.port") == 9000
    assert cfg.get("app.timezone") == "Asia/Shanghai"


def test_secret_update_skips_masked_and_empty(paths):
    cfg = ConfigManager(paths)
    cfg.update_secrets({"llm": {"openai_compat": {"api_key": "sk-abcdefgh12345678"}}})
    cfg.update_secrets({"llm": {"openai_compat": {"api_key": mask_secret("sk-abcdefgh12345678")}}})
    cfg.update_secrets({"llm": {"openai_compat": {"api_key": ""}}})
    assert cfg.secret("llm.openai_compat.api_key") == "sk-abcdefgh12345678"
    masked = cfg.masked_secrets()
    assert "app" not in masked
    assert masked["llm"]["openai_compat"]["api_key"] == "••••5678"


def test_mask_helpers():
    assert mask_secret("abcdefgh1234") == "••••1234"
    assert mask_secret("short") == "••••"
    assert mask_secret("") == "" and mask_secret(None) == ""
    assert is_masked("••••1234") and not is_masked("abcd")
    assert is_unchanged_secret("") and is_unchanged_secret("••••1234") and not is_unchanged_secret("new-key")
    assert mask_tree({"a": "1234567890", "b": {"c": ""}}) == {"a": "••••7890", "b": {"c": ""}}
    assert "sk-secret-value" not in redact_text("key=sk-secret-value", ["sk-secret-value"])
    assert "abc123" not in redact_text("GET /api/events?token=abc123&x=1", [])
