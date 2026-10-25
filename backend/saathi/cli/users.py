"""Create or reset a staff account.

    python -m saathi.cli.users add --username imran --name "Imran Shaikh" --role desk
    python -m saathi.cli.users dev-users

The password is asked for at the terminal, never passed as an argument, so it
does not end up in shell history or the process list.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from ..adapters.identity import LocalIdentity
from ..adapters.records.sql import migrate
from ..config import get_settings
from ..domain.enums import Role

#: Local development only. `dev-users` refuses to run in production.
DEV_USERS = (
    ("seema", "Seema Kamble", Role.NAVIGATOR),
    ("imran", "Imran Shaikh", Role.DESK),
    ("amrita", "Dr Amrita Sinha", Role.DOCTOR),
    ("neha", "Neha", Role.ADMIN),
)
DEV_PASSWORD = "saathi-dev"


class _NoFamilies:
    def families_for(self, phone: str):
        return ()


def _identity() -> LocalIdentity:
    settings = get_settings()
    migrate(settings.records_url)
    return LocalIdentity(settings.records_url, secret="cli", phones=_NoFamilies())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saathi-users")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="create or reset one staff account")
    add.add_argument("--username", required=True)
    add.add_argument("--name", required=True)
    staff = [r.value for r in Role if r.value not in ("patient", "caregiver")]
    add.add_argument("--role", required=True, choices=staff)
    sub.add_parser("dev-users", help=f"create four dev accounts, password {DEV_PASSWORD!r}")
    args = parser.parse_args(argv)

    identity = _identity()
    if args.command == "add":
        password = getpass.getpass("password: ")
        if password != getpass.getpass("again: "):
            print("the two did not match", file=sys.stderr)
            return 1
        identity.add_user(args.username, args.name, Role(args.role), password)
        print(f"saved {args.username} ({args.role})")
        return 0

    if get_settings().environment.lower() == "production":
        print("dev-users will not run in production", file=sys.stderr)
        return 1
    for username, name, role in DEV_USERS:
        identity.add_user(username, name, role, DEV_PASSWORD)
        print(f"{username:8} {role.value:10} password: {DEV_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
