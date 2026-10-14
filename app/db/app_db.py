"""Schema for app.db: users, conversations, messages, agent calls and the admin audit log."""
from __future__ import annotations

from pathlib import Path

from app.db.connection import init_schema

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin')),
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    last_login_at  TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    title           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    is_deleted      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(conversation_id),
    sender          TEXT NOT NULL CHECK (sender IN ('customer', 'assistant')),
    content         TEXT NOT NULL,
    categories      TEXT,
    meta            TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, message_id);

CREATE TABLE IF NOT EXISTS agent_calls (
    call_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id      INTEGER NOT NULL REFERENCES messages(message_id),
    agent           TEXT NOT NULL,
    sub_question    TEXT NOT NULL,
    filters         TEXT,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'empty', 'failed')),
    products_found  INTEGER NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_calls_message ON agent_calls(message_id);

CREATE TABLE IF NOT EXISTS admin_audit (
    audit_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id        INTEGER NOT NULL REFERENCES users(user_id),
    viewed_user_id  INTEGER NOT NULL REFERENCES users(user_id),
    conversation_id INTEGER,
    viewed_at       TEXT NOT NULL
);
"""


def init_app_db(path: Path) -> None:
    init_schema(path, APP_SCHEMA)
