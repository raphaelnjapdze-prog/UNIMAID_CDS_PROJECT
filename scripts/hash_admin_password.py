"""Generate an ADMIN_PASSWORD_HASH for the local-admin fallback login.

    python scripts/hash_admin_password.py
    python scripts/hash_admin_password.py --iterations 300000

Prompts for the password (twice, hidden), then prints the PBKDF2-SHA256 hash
string to paste into your secrets as ADMIN_PASSWORD_HASH. Storing this hash lets
you drop the plaintext ADMIN_PASSWORD entirely — no admin password ever lives in
secrets.toml/env. See utils.auth.hash_admin_password / _verify_admin_password.

Exits 0 on success, 2 on a usage error (e.g. mismatched/empty password).
"""

import argparse
import getpass
import sys
from pathlib import Path

# The script lives in scripts/, so the repo root isn't on sys.path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.auth import _PBKDF2_DEFAULT_ITERATIONS, hash_admin_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an ADMIN_PASSWORD_HASH value.")
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

    password = getpass.getpass("Admin password: ")
    if not password:
        print("error: password must not be empty", file=sys.stderr)
        return 2
    if password != getpass.getpass("Confirm password: "):
        print("error: passwords did not match", file=sys.stderr)
        return 2

    digest = hash_admin_password(password, iterations=args.iterations)
    print("\nAdd this to your secrets (.streamlit/secrets.toml) or environment:\n")
    print(f'ADMIN_PASSWORD_HASH = "{digest}"')
    print("\nThen remove any plaintext ADMIN_PASSWORD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
