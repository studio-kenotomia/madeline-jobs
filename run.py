#!/usr/bin/env python3
"""Run one discovery cycle. Used by GitHub Actions and, for testing, by the Mac."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=str(ROOT / "state" / "state.enc"))
    parser.add_argument("--site", default=str(ROOT / "site"))
    parser.add_argument("--media", default=str(ROOT / "media"))
    parser.add_argument("--mode", choices=["full", "inbox"], default="full")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--primary", action="store_true", help="Allowed to send email. Exactly one host should pass this.")
    args = parser.parse_args()
    key = os.environ.get("DASH_KEY", "")
    if len(key) < 16:
        raise SystemExit("DASH_KEY is missing.")
    cycle = pipeline.run(state_path=Path(args.state), site_out=Path(args.site) if args.site else None, key=key, primary=args.primary, mode=args.mode, only=args.only, force=args.force, media_dir=Path(args.media))
    print(json.dumps({k: v for k, v in cycle.items() if k != "sources"} | {"sources_run": len(cycle["sources"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
