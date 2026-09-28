"""Generate a Werkzeug password hash for PULSEWATCH_PASSWORD_HASH."""

import getpass
import sys

from werkzeug.security import generate_password_hash


def main() -> None:
    password = getpass.getpass("Admin password: ")
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        sys.exit(1)
    print(generate_password_hash(password, method="pbkdf2:sha256:600000"))


if __name__ == "__main__":
    main()
