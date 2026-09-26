"""Generate local deployment secrets. Never prints secrets or overwrites .env."""
import argparse
import os
import re
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Create SongDown deployment configuration")
    parser.add_argument("--domain", required=True, help="Public hostname, e.g. music.example.com")
    parser.add_argument("--output", default=".env")
    args = parser.parse_args()
    if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", args.domain):
        parser.error("Use a hostname without scheme, path or port")
    path = Path(args.output)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        parser.error(f"{path} already exists; edit it explicitly instead of overwriting secrets")
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"SITE_DOMAIN={args.domain}\nWEB_ACCESS_TOKEN={secrets.token_urlsafe(32)}\nWEB_SECRET_KEY={secrets.token_hex(32)}\n")
    print(f"Created {path}. Keep this file private. Use WEB_ACCESS_TOKEN to sign in.")


if __name__ == "__main__":
    main()
