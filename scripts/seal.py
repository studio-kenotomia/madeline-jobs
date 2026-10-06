#!/usr/bin/env python3
"""Seal or unseal the private profile and photo. The sealed files are safe to commit."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import crypto  # noqa: E402

PAIRS = [(ROOT / "profile.json", ROOT / "data" / "profile.enc"), (ROOT / "data" / "photo.png", ROOT / "data" / "photo.enc")]


def main() -> None:
    key = os.environ.get("DASH_KEY", "")
    if len(key) < 16:
        raise SystemExit("DASH_KEY is missing.")
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    for plain, sealed in PAIRS:
        if action == "seal":
            if plain.exists():
                sealed.write_text(crypto.encrypt_bytes(key, plain.read_bytes()))
                print("sealed", sealed.name)
        elif action == "unseal":
            if sealed.exists():
                plain.parent.mkdir(parents=True, exist_ok=True)
                plain.write_bytes(crypto.decrypt_bytes(key, sealed.read_text()))
                print("unsealed", plain.name)
        else:
            raise SystemExit("usage: seal.py seal|unseal")


if __name__ == "__main__":
    main()
