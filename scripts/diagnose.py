#!/usr/bin/env python3
"""Run hardware / toolchain diagnostics and write docs/HARDWARE_REPORT.md.

Usage:
    python scripts/diagnose.py [--no-encoder-test] [--json]
Reads ACESTEP_DIR / ACESTEP_API_URL from .env if present (no secrets are printed).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.hardware import full_diagnostics, render_markdown  # noqa: E402


def _load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-encoder-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "docs" / "HARDWARE_REPORT.md"))
    args = ap.parse_args()
    _load_env()
    work = ROOT / "data" / "tmp"
    work.mkdir(parents=True, exist_ok=True)
    diag = full_diagnostics(
        acestep_dir=os.environ.get("ACESTEP_DIR") or None,
        api_url=os.environ.get("ACESTEP_API_URL") or None,
        run_encoder_tests=not args.no_encoder_test,
        workdir=work,
    )
    md = render_markdown(diag)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    (ROOT / "data" / "hardware_report.json").write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(diag, ensure_ascii=False, indent=2))
    else:
        print(md)
    print(f"[diagnose] wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
