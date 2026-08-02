"""Generate an ADMIN_DELETE_PASSKEY_HASH for the admin bulk-delete gate.

    python scripts/hash_admin_passkey.py
    python scripts/hash_admin_passkey.py --iterations 300000

Prompts for the passkey (twice, hidden), then prints the PBKDF2-SHA256 hash string
to paste into your secrets as ADMIN_DELETE_PASSKEY_HASH. The passkey itself is never
written anywhere — only its hash — so losing it means generating a new one, not
recovering the old.

This is the prompt shown before "delete every entry in the project", on top of the
account already being registered in public.app_admins. It is a confirmation step, not
the security boundary: who may delete what is enforced by RLS
(sql/add_ownership_delete_policies.sql). What it prevents is an unattended admin
session, or a misclick, emptying the project.

Until this is set the bulk delete stays disabled — see utils.auth.verify_admin_passkey,
which fails closed rather than defaulting to open.

Exits 0 on success, 2 on a usage error (e.g. mismatched/empty passkey).
"""

import argparse
import getpass
import sys
from pathlib import Path

# The script lives in scripts/, so the repo root isn't on sys.path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.auth import _PBKDF2_DEFAULT_ITERATIONS, hash_admin_password  # noqa: E402

# Short enough to type under pressure is not the goal here — this guards "delete
# everything", it is entered rarely, and it should be pasted from a password manager.
_MIN_PASSKEY_LENGTH = 12


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an ADMIN_DELETE_PASSKEY_HASH value.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=_PBKDF2_DEFAULT_ITERATIONS,
        help=f"PBKDF2 iteration count (default: {_PBKDF2_DEFAULT_ITERATIONS}).",
    )
    args = parser.parse_args()

    if args.iterations < 1:
        print("error: --iterations must be a positive integer", file=sys.stderr)
        return 2

    passkey = getpass.getpass("Admin delete passkey: ")
    if not passkey:
        print("error: passkey must not be empty", file=sys.stderr)
        return 2
    if len(passkey) < _MIN_PASSKEY_LENGTH:
        print(
            f"error: passkey must be at least {_MIN_PASSKEY_LENGTH} characters — "
            "this one guards deleting every entry in the project",
            file=sys.stderr,
        )
        return 2
    if passkey != getpass.getpass("Confirm passkey: "):
        print("error: passkeys did not match", file=sys.stderr)
        return 2

    digest = hash_admin_password(passkey, iterations=args.iterations)
    print("\nAdd this to your secrets (.streamlit/secrets.toml) or environment:\n")
    print(f'ADMIN_DELETE_PASSKEY_HASH = "{digest}"')
    print(
        "\nStore the passkey itself in a password manager — only the hash is kept here,\n"
        "so it cannot be recovered from the app or this repository."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
