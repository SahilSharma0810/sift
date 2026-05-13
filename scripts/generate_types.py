#!/usr/bin/env python3
"""Generate frontend TypeScript types from backend Pydantic models.

Run at build time (CI + pre-commit). Output goes to
frontend/src/types/generated/. Hand-editing the generated file is forbidden.

Per ADR-0005: eliminates the "model changed, TS type didn't" bug class.

Usage:
    python scripts/generate_types.py [--check]

    --check  : exit 1 if generated types are out of date (CI guard).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "types" / "generated" / "domain.ts"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the generated file is out of date (CI guard).",
    )
    args = parser.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)

    # We use the `pydantic2ts` CLI which generates a single .ts file from a
    # Python module path. The module imports all our public domain types.
    cmd = [
        "pydantic2ts",
        "--module",
        "backend.app.domain.models",
        "--output",
        str(OUT),
    ]

    if args.check:
        # Run to a temp file, diff against OUT, exit 1 on diff.
        tmp = OUT.with_suffix(".ts.check")
        cmd[-1] = str(tmp)
        subprocess.run(cmd, check=True, cwd=ROOT)
        if not OUT.exists() or OUT.read_bytes() != tmp.read_bytes():
            tmp.unlink(missing_ok=True)
            print("ERROR: generated types are out of date. Run scripts/generate_types.py.")
            return 1
        tmp.unlink(missing_ok=True)
        return 0

    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
