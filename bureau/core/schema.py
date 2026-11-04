"""数据库结构（§12）。迁移按 ``PRAGMA user_version`` 顺序执行，只能追加，不能改已有字段的含义。"""

from __future__ import annotations

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS groups (
    key TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    native_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    alias TEXT,
    member_count INTEGER,
    avatar_url TEXT,
    whitelisted INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    is_demo INTEGER NOT NULL DEFAULT 0,
    extra TEXT NOT NULL DEFAULT '{}',
    last_message_at TEXT,
    last_collect_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_groups_platform ON groups(platform, whitelisted);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_key TEXT NOT NULL REFERENCES groups(key) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    native_id TEXT NOT NULL,
    sender_id TEXT,
    sender_name TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL,
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL DEFAULT '',
    reply_to TEXT,
    quote_text TEXT,
    mentions TEXT NOT NULL DEFAULT '[]',
    attachments TEXT NOT NULL DEFAULT '[]',
    is_self INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'collect',
    created_at TEXT NOT NULL,
    UNIQUE(group_key, native_id)
);
CREATE INDEX IF NOT EXISTS ix_messages_group_ts ON messages(group_key, ts);
CREATE INDEX IF NOT EXISTS ix_messages_ts ON messages(ts);

CREATE TABLE IF NOT EXISTS cursors (
    group_key TEXT PRIMARY KEY REFERENCES groups(key) ON DELETE CASCADE,
    last_ts TEXT,
    last_native_id TEXT,
    collector_cursor TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 0,
    is_demo INTEGER NOT NULL DEFAULT 0,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    totals TEXT NOT NULL DEFAULT '{}',
    report_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_runs_created ON runs(created_at);

CREATE TABLE IF NOT EXISTS run_stages (
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    seq INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    metrics TEXT NOT NULL DEFAULT '{}',
    message TEXT,
    PRIMARY KEY (run_id, name)
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    stage TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_run_logs_run ON run_logs(run_id, id);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    date_label TEXT NOT NULL,
    window_label TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    is_demo INTEGER NOT NULL DEFAULT 0,
    dry_run INTEGER NOT NULL DEFAULT 0,
    items_total INTEGER NOT NULL DEFAULT 0,
    headlines TEXT NOT NULL DEFAULT '[]',
    judgments TEXT NOT NULL DEFAULT '[]',
    stats TEXT NOT NULL DEFAULT '{}',
    full_md TEXT NOT NULL DEFAULT '',
    summary_md TEXT NOT NULL DEFAULT '',
    summary_text TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_created ON reports(created_at);

CREATE TABLE IF NOT EXISTS intel_items (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    kind TEXT NOT NULL,
    score REAL NOT NULL,
    trend TEXT NOT NULL,
    is_headline INTEGER NOT NULL DEFAULT 0,
    is_feature INTEGER NOT NULL DEFAULT 0,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_items_report ON intel_items(report_id, rank);

CREATE TABLE IF NOT EXISTS topic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL DEFAULT 'live',
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    links TEXT NOT NULL DEFAULT '[]',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    history TEXT NOT NULL DEFAULT '[]',
    last_item_id TEXT,
    heat REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_memory_scope ON topic_memory(scope, last_seen);

CREATE TABLE IF NOT EXISTS keyword_daily (
    scope TEXT NOT NULL DEFAULT 'live',
    day TEXT NOT NULL,
    word TEXT NOT NULL,
    count INTEGER NOT NULL,
    groups TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (scope, day, word)
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    cron TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
    window_mode TEXT NOT NULL DEFAULT 'since_last',
    window_hours INTEGER NOT NULL DEFAULT 24,
    platforms TEXT NOT NULL DEFAULT '[]',
    group_keys TEXT NOT NULL DEFAULT '[]',
    channel_ids TEXT NOT NULL DEFAULT '[]',
    top_n INTEGER NOT NULL DEFAULT 5,
    dry_run INTEGER NOT NULL DEFAULT 0,
    last_fire_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    config TEXT NOT NULL DEFAULT '{}',
    last_ok INTEGER,
    last_detail TEXT,
    last_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    run_id TEXT,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    ok INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    external_id TEXT,
    parts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deliveries_report ON deliveries(report_id);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

FTS_TEMPLATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, sender_name, content='messages', content_rowid='id', tokenize='{tokenizer}'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, sender_name) VALUES (new.id, new.text, new.sender_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, sender_name) VALUES ('delete', old.id, old.text, old.sender_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text, sender_name ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, sender_name) VALUES ('delete', old.id, old.text, old.sender_name);
    INSERT INTO messages_fts(rowid, text, sender_name) VALUES (new.id, new.text, new.sender_name);
END;
"""

# v2（docs/V2_KNOWLEDGE.md）：只增加表和列，不改已有字段，v1 代码在新结构上照常运行
SCHEMA_V2 = """
ALTER TABLE reports ADD COLUMN v2_data TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS kb_articles (
    rid INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    scope TEXT NOT NULL DEFAULT 'live',
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    hook TEXT NOT NULL DEFAULT '',
    risk_flags TEXT NOT NULL DEFAULT '[]',
    fingerprint TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    links TEXT NOT NULL DEFAULT '[]',
    body_md TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]',
    first_day TEXT NOT NULL,
    last_day TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_scope_updated ON kb_articles(scope, updated_at);
CREATE INDEX IF NOT EXISTS ix_kb_fingerprint ON kb_articles(scope, fingerprint);

CREATE TABLE IF NOT EXISTS kb_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
    report_id TEXT NOT NULL DEFAULT '',
    day TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body_md TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kb_versions_kb ON kb_versions(kb_id, id);
"""

KB_FTS_TEMPLATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    title, body_md, tags, content='kb_articles', content_rowid='rid', tokenize='{tokenizer}'
);
CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON kb_articles BEGIN
    INSERT INTO kb_fts(rowid, title, body_md, tags) VALUES (new.rid, new.title, new.body_md, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS kb_ad AFTER DELETE ON kb_articles BEGIN
    INSERT INTO kb_fts(kb_fts, rowid, title, body_md, tags) VALUES ('delete', old.rid, old.title, old.body_md, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS kb_au AFTER UPDATE OF title, body_md, tags ON kb_articles BEGIN
    INSERT INTO kb_fts(kb_fts, rowid, title, body_md, tags) VALUES ('delete', old.rid, old.title, old.body_md, old.tags);
    INSERT INTO kb_fts(rowid, title, body_md, tags) VALUES (new.rid, new.title, new.body_md, new.tags);
END;
"""

# 迁移列表：下标 i 对应 user_version 从 i 升到 i+1
MIGRATIONS: list[str] = [SCHEMA_V1, SCHEMA_V2]
LATEST_VERSION = len(MIGRATIONS)
