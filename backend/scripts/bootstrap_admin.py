"""Create the first admin account using explicit operator input.

Usage (run from backend/):
    ADMIN_EMAIL=admin@example.com python scripts/bootstrap_admin.py

The password is read from ADMIN_PASSWORD or securely prompted. No default
admin credentials are accepted.
"""
import asyncio
import getpass
import os
import sys

from app.core.database import close_db, connect_db, get_db
from app.services.auth_service import register_user
from app.models import user_model


async def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    name = os.environ.get("ADMIN_NAME", "Shoply Administrator").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")

    if not email:
        print("ADMIN_EMAIL is required", file=sys.stderr)
        return 2
    if not password:
        password = getpass.getpass("Admin password: ")
    if len(password) < 8:
        print("Admin password must contain at least 8 characters", file=sys.stderr)
        return 2

    await connect_db()
    try:
        db = get_db()
        existing = await user_model.find_by_email(db, email)
        if existing:
            if existing.get("role") != "admin":
                print("A non-admin account already uses this email", file=sys.stderr)
                return 1
            print("Admin account already exists; no changes made.")
            return 0

        result = await register_user(db, name, email, password, "admin")
        print(f"Admin account created: {result['user_id']}")
        return 0
    finally:
        await close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
