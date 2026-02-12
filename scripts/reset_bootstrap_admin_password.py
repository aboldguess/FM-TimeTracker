#!/usr/bin/env python3
"""Mini-README: CLI utility to rotate bootstrap admin credentials safely.

Use this when a local environment has already completed first startup and
changing `.env` no longer updates the seeded bootstrap admin password.
"""

from __future__ import annotations

import argparse
import os
import sys

from app.bootstrap_admin import reset_bootstrap_admin_password
from app.config import settings
from app.database import engine


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reset the bootstrap admin password (stored hashed) and force a password "
            "change at next login."
        )
    )
    parser.add_argument(
        "--password",
        dest="password",
        default=None,
        help="New plaintext password. If omitted, BOOTSTRAP_ADMIN_PASSWORD from environment is used.",
    )
    parser.add_argument(
        "--email",
        dest="email",
        default=None,
        help="Optional bootstrap admin email override. Defaults to BOOTSTRAP_ADMIN_EMAIL.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    password = (args.password or os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or settings.bootstrap_admin_password).strip()

    if not password:
        print("[bootstrap-reset] ERROR: no password provided via --password or BOOTSTRAP_ADMIN_PASSWORD.")
        return 1

    updated = reset_bootstrap_admin_password(
        engine=engine,
        new_password=password,
        bootstrap_email=args.email,
    )
    if not updated:
        print("[bootstrap-reset] ERROR: bootstrap admin account was not found.")
        return 2

    effective_email = args.email or settings.bootstrap_admin_email
    print(
        "[bootstrap-reset] Success: updated bootstrap admin password for "
        f"{effective_email} and set must_change_password=true."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
