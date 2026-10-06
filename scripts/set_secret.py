#!/usr/bin/env python3
"""Store a GitHub Actions secret without it touching the repository or shell history.

Usage: .venv/bin/python scripts/set_secret.py RESEND_API_KEY   (then paste the value and press Enter)
"""

from __future__ import annotations

import base64
import getpass
import json
import subprocess
import sys
import urllib.request

REPO = "studio-kenotomia/madeline-jobs"


def token() -> str:
    result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True)
    return next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("password="))


def call(method: str, path: str, payload=None):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}{path}", method=method, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json", "User-Agent": "radar", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        body = response.read().decode()
        return json.loads(body) if body else {}


def main() -> None:
    from nacl import encoding, public

    name = sys.argv[1]
    value = getpass.getpass(f"{name}: ").strip()
    if not value:
        raise SystemExit("Nothing entered.")
    key = call("GET", "/actions/secrets/public-key")
    sealed = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder())).encrypt(value.encode())
    call("PUT", f"/actions/secrets/{name}", {"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key["key_id"]})
    print(f"{name} saved as a GitHub secret.")


if __name__ == "__main__":
    main()
