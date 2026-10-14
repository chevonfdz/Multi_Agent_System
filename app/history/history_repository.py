"""Conversations, messages and agent calls (FR-1, FR-10)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.text_utils import utc_now


@dataclass
class Conversation:
    conversation_id: int
    user_id: int
    title: str
    created_at: str
    updated_at: str
    is_deleted: bool

    def public(self) -> dict:
        return {"conversation_id": self.conversation_id, "user_id": self.user_id, "title": self.title,
                "created_at": self.created_at, "updated_at": self.updated_at,
                "is_deleted": self.is_deleted}


@dataclass
class Message:
    message_id: int
    conversation_id: int
    sender: str
    content: str
    categories: list[str]
    meta: dict[str, Any]
    created_at: str
    agent_calls: list[dict[str, Any]] = field(default_factory=list)

    def public(self, include_calls: bool = False) -> dict:
        data = {"message_id": self.message_id, "sender": self.sender, "content": self.content,
                "categories": self.categories, "created_at": self.created_at}
        if include_calls:
            data["agent_calls"] = self.agent_calls
        return data


def _to_conversation(row) -> Conversation:
    return Conversation(conversation_id=row["conversation_id"], user_id=row["user_id"],
                        title=row["title"], created_at=row["created_at"],
                        updated_at=row["updated_at"], is_deleted=bool(row["is_deleted"]))


def _to_message(row) -> Message:
    categories = [c for c in (row["categories"] or "").split(",") if c]
    try:
        meta = json.loads(row["meta"]) if row["meta"] else {}
    except json.JSONDecodeError:
        meta = {}
    return Message(message_id=row["message_id"], conversation_id=row["conversation_id"],
                   sender=row["sender"], content=row["content"], categories=categories,
                   meta=meta, created_at=row["created_at"])


def make_title(message: str) -> str:
    title = " ".join(message.split())
    return title if len(title) <= 60 else title[:57].rstrip() + "..."


class HistoryRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ------------------------------------------------------------ conversations
    def create_conversation(self, user_id: int, first_message: str) -> Conversation:
        now = utc_now()
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, make_title(first_message), now, now))
            conversation_id = int(cur.lastrowid)
        return self.get_conversation(conversation_id)  # type: ignore[return-value]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM conversations WHERE conversation_id = ?",
                               (conversation_id,)).fetchone()
        return _to_conversation(row) if row else None

    def list_conversations(self, user_id: int, include_deleted: bool = False) -> list[Conversation]:
        sql = "SELECT * FROM conversations WHERE user_id = ?"
        if not include_deleted:
            sql += " AND is_deleted = 0"
        sql += " ORDER BY updated_at DESC, conversation_id DESC"
        with connect(self.db_path) as conn:
            return [_to_conversation(r) for r in conn.execute(sql, (user_id,)).fetchall()]

    def soft_delete(self, conversation_id: int) -> None:
        # OQ-2 default: hidden from the customer, still visible to admins.
        with connect(self.db_path) as conn:
            conn.execute("UPDATE conversations SET is_deleted = 1 WHERE conversation_id = ?",
                         (conversation_id,))

    # ------------------------------------------------------------ messages
    def load_recent(self, conversation_id: int, last_n: int = 10) -> list[Message]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY message_id DESC LIMIT ?",
                (conversation_id, last_n)).fetchall()
        return [_to_message(r) for r in reversed(rows)]

    def messages(self, conversation_id: int, include_calls: bool = False) -> list[Message]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY message_id",
                                (conversation_id,)).fetchall()
            result = [_to_message(r) for r in rows]
            if include_calls and result:
                ids = [m.message_id for m in result]
                marks = ", ".join("?" for _ in ids)
                calls = conn.execute(f"SELECT * FROM agent_calls WHERE message_id IN ({marks}) "
                                     f"ORDER BY call_id", ids).fetchall()
                by_message: dict[int, list[dict]] = {}
                for c in calls:
                    item = dict(c)
                    item["filters"] = json.loads(item["filters"]) if item.get("filters") else {}
                    by_message.setdefault(item["message_id"], []).append(item)
                for m in result:
                    m.agent_calls = by_message.get(m.message_id, [])
        return result

    def save_turn(self, conversation_id: int, customer_text: str, reply_text: str,
                  categories: list[str], meta: dict[str, Any],
                  agent_calls: list[dict[str, Any]]) -> tuple[int, int]:
        """Saves the customer message, the assistant reply and one agent_calls row per task."""
        now = utc_now()
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, sender, content, created_at) VALUES (?, 'customer', ?, ?)",
                (conversation_id, customer_text, now))
            customer_id = int(cur.lastrowid)
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, sender, content, categories, meta, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?, ?)",
                (conversation_id, reply_text, ",".join(categories) or None, json.dumps(meta), utc_now()))
            assistant_id = int(cur.lastrowid)
            for call in agent_calls:
                conn.execute(
                    "INSERT INTO agent_calls (message_id, agent, sub_question, filters, status, "
                    "products_found, latency_ms, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (assistant_id, call["agent"], call["sub_question"], json.dumps(call.get("filters") or {}),
                     call["status"], int(call.get("products_found", 0)), int(call.get("latency_ms", 0)),
                     call.get("error")))
            conn.execute("UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                         (utc_now(), conversation_id))
        return customer_id, assistant_id

    def agent_call_count(self, message_id: int) -> int:
        with connect(self.db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM agent_calls WHERE message_id = ?",
                                    (message_id,)).fetchone()["n"])
