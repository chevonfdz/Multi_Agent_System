"""Audit log of admin access to user chat histories (UM-8)."""
from __future__ import annotations

from pathlib import Path

from app.db.connection import connect
from app.text_utils import utc_now


class AuditRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def record(self, admin_id: int, viewed_user_id: int, conversation_id: int | None = None) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO admin_audit (admin_id, viewed_user_id, conversation_id, viewed_at) "
                "VALUES (?, ?, ?, ?)", (admin_id, viewed_user_id, conversation_id, utc_now()))

    def recent(self, limit: int = 100) -> list[dict]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT a.audit_id, a.viewed_at, a.conversation_id, "
                "ad.user_id AS admin_id, ad.name AS admin_name, ad.email AS admin_email, "
                "u.user_id AS viewed_user_id, u.name AS viewed_user_name, u.email AS viewed_user_email "
                "FROM admin_audit a JOIN users ad ON ad.user_id = a.admin_id "
                "JOIN users u ON u.user_id = a.viewed_user_id "
                "ORDER BY a.audit_id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def count_for(self, admin_id: int, viewed_user_id: int) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM admin_audit WHERE admin_id = ? AND viewed_user_id = ?",
                               (admin_id, viewed_user_id)).fetchone()
        return int(row["n"])
