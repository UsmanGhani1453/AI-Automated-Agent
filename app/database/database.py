"""
SQLite persistence layer.

Design notes:
- One connection per call (SQLite + threads/async don't mix well otherwise).
  For a laptop-scale, single-user agent this is fine — no connection pool needed.
- WAL mode so the API server and any background scheduler can read/write concurrently.
- Every table that matters for learning/explainability is created here so the whole
  schema lives in one place and is easy to audit.
"""
import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("AGENT_DB_PATH", "agent.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER,
    goal TEXT,
    current_task TEXT,
    current_lead_id INTEGER,
    memory_context TEXT,
    selected_strategy TEXT,
    quality_score REAL,
    action TEXT,
    result TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    officer TEXT,
    company TEXT,
    fleet_size TEXT,
    location TEXT,
    email TEXT,
    category TEXT,
    status TEXT DEFAULT 'new',        -- new, contacted, skipped, suppressed, invalid
    last_contacted_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppression_list (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    goal TEXT,
    status TEXT DEFAULT 'pending',    -- pending, in_progress, done, failed
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    steps_json TEXT,                  -- ordered list of planned steps
    current_step INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    plan_step INTEGER,
    action_type TEXT,
    parameters_json TEXT,
    status TEXT,                      -- success, failed, retried, skipped
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    strategy TEXT,
    components_json TEXT,             -- which component ids were used (greeting/cta/etc)
    body TEXT,
    quality_score REAL,
    analyzer_report_json TEXT,
    version INTEGER DEFAULT 1,        -- increments on regeneration
    user_edited_body TEXT,
    approved INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    sent_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS email_components (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_type TEXT,              -- greeting, opening, value_prop, service, cta, signature
    text TEXT,
    positive_score REAL DEFAULT 0.5,  -- normalized 0-1, starts neutral
    uses INTEGER DEFAULT 0,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(component_type, text)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER,
    rating INTEGER,                   -- 1-5
    action TEXT,                      -- approve, edit, reject
    comment TEXT,
    replied INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    email_id INTEGER,
    context_json TEXT,
    decision_json TEXT,
    evaluation_json TEXT,
    outcome TEXT,
    feedback_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT,                 -- episodic, semantic
    content_json TEXT,
    tags TEXT,
    importance REAL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learned_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_key TEXT UNIQUE,          -- e.g. "strategy:SHORT_DIRECT" or "cta:len<20"
    description TEXT,
    score REAL DEFAULT 0.5,
    positive_feedback INTEGER DEFAULT 0,
    negative_feedback INTEGER DEFAULT 0,
    reply_count INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS learned_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_key TEXT UNIQUE,       -- e.g. "prefers_short_openings"
    description TEXT,
    confidence REAL DEFAULT 0.0,
    evidence_count INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT,
    parameters_json TEXT,
    result_json TEXT,
    status TEXT,
    duration_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT,
    metric_value REAL,
    context_json TEXT,
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def dumps(obj):
    return json.dumps(obj, default=str)


def loads(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default
