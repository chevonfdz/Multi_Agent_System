"""Users table access."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.db.connection import connect
from app.text_utils import utc_now


@dataclass
class User:
    user_id: int
    name: str
    email: str
    password_hash: str
    role: str
    is_active: bool
    created_at: str
    last_login_at: str | None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict:
        return {"user_id": self.user_id, "name": self.name, "email": self.email, "role": self.role,
                "is_active": self.is_active, "created_at": self.created_at,
                "last_login_at": self.last_login_at}


def _row_to_user(row) -> User:
    return User(user_id=row["user_id"], name=row["name"], email=row["email"],
                password_hash=row["password_hash"], role=row["role"],
                is_active=bool(row["is_active"]), created_at=row["created_at"],
                last_login_at=row["last_login_at"])


class UserRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def create(self, name: str, email: str, password_hash: str, role: str = "customer") -> User:
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)", (name, email.lower(), password_hash, role, utc_now()))
            user_id = int(cur.lastrowid)
        return self.get(user_id)  # type: ignore[return-value]

    def get(self, user_id: int) -> User | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return _row_to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return _row_to_user(row) if row else None

    def search(self, text: str = "", limit: int = 200) -> list[User]:
        sql = "SELECT * FROM users"
        args: list = []
        if text:
            sql += " WHERE name LIKE ? OR email LIKE ?"
            args = [f"%{text}%", f"%{text}%"]
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with connect(self.db_path) as conn:
            return [_row_to_user(r) for r in conn.execute(sql, args).fetchall()]

    def touch_login(self, user_id: int) -> None:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?", (utc_now(), user_id))

    def set_active(self, user_id: int, active: bool) -> None:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (1 if active else 0, user_id))

    def set_role(self, user_id: int, role: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))

    def set_password(self, user_id: int, password_hash: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id))
