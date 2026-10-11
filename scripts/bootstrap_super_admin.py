"""Create the first Neyan AI super-admin account from a trusted shell."""

import argparse
import getpass
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.security.admin_bootstrap import BootstrapError, provision_first_super_admin
from database.init_db import initialize_database


def _password_from_input(use_stdin):
    if use_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            raise BootstrapError("No password was provided on standard input.")
        return password

    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise BootstrapError("Passwords do not match.")
    return password


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Provision the first Neyan AI super admin. This command never resets an existing admin."
    )
    parser.add_argument("--name", required=True, help="Full name for the operator account")
    parser.add_argument("--email", required=True, help="Email address for the operator account")
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from stdin.")
    args = parser.parse_args(argv)

    try:
        password = _password_from_input(args.password_stdin)
        initialize_database()
        result = provision_first_super_admin(args.name, args.email, password)
    except BootstrapError as exc:
        print(f"Bootstrap not performed: {exc}", file=sys.stderr)
        return 2

    print(f"First super admin created for {result.email} (user_id={result.user_id}).")
    print("No password was printed. Store it in your approved secret manager.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
