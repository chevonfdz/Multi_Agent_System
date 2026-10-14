"""Create (or promote) an admin account (UM-7). Admins cannot be created from the website.

    python scripts/create_admin.py --email admin@example.com --name "Site Admin"

You are asked for the password unless you pass --password.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.schemas import RegisterRequest  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.db.app_db import init_app_db  # noqa: E402
from app.users.user_repository import UserRepository  # noqa: E402
from config.settings import Settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote an admin account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Admin")
    parser.add_argument("--password", help="If omitted you will be prompted (recommended).")
    args = parser.parse_args()

    settings = Settings.from_env()
    init_app_db(settings.app_db_path)
    users = UserRepository(settings.app_db_path)

    password = args.password
    if not password:
        password = getpass.getpass("Password (8-72 characters): ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.")
            return 1
    try:
        body = RegisterRequest(name=args.name, email=args.email, password=password)
    except Exception as exc:
        print(f"Invalid input: {exc}")
        return 1

    existing = users.get_by_email(body.email)
    if existing:
        users.set_role(existing.user_id, "admin")
        users.set_password(existing.user_id, hash_password(body.password))
        users.set_active(existing.user_id, True)
        print(f"Existing user {body.email} is now an admin (password updated).")
    else:
        users.create(body.name, body.email, hash_password(body.password), role="admin")
        print(f"Admin account created for {body.email}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
