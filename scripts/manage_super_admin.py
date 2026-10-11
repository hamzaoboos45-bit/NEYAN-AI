"""Safely identify or reset an existing Neyan AI super-admin from a trusted shell."""

import argparse
import getpass
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.security.admin_management import AdminManagementError, list_super_admins, reset_super_admin_password
from database.init_db import initialize_database


def _password_from_input(password_stdin: bool) -> str:
    if password_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Confirm new password: ")
    if first != second:
        raise AdminManagementError("Passwords did not match.")
    return first


def main(argv=None):
    parser = argparse.ArgumentParser(description="Safely identify or reset an existing Neyan AI super-admin.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="List enabled super-admin email addresses only")
    action.add_argument("--reset-password", action="store_true", help="Reset one enabled super-admin password")
    parser.add_argument("--email", help="Platform super-admin email address (required with --reset-password)")
    parser.add_argument("--password-stdin", action="store_true", help="Read one password from standard input without echoing it")
    args = parser.parse_args(argv)

    if args.reset_password and not args.email:
        parser.error("--email is required with --reset-password")
    if args.list and (args.email or args.password_stdin):
        parser.error("--email and --password-stdin are only valid with --reset-password")

    try:
        initialize_database()
        if args.list:
            admins = list_super_admins()
            if not admins:
                print("No enabled super-admin account exists. Use bootstrap_super_admin.py to create the first one.")
                return 0
            for admin in admins:
                print(admin.email)
            return 0
        admin = reset_super_admin_password(args.email, _password_from_input(args.password_stdin))
    except AdminManagementError as exc:
        print(f"Admin access update not performed: {exc}", file=sys.stderr)
        return 2

    print(f"Password reset for {admin.email}. Remembered sessions were revoked.")
    print("No password or password hash was printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
