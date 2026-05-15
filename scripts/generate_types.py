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
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "types" / "generated" / "domain.ts"

# pydantic2ts marks `type` optional in each reason interface because the
# Python models give it a Literal default. The runtime always serializes
# it, so flip the discriminator to required to make exhaustive unions work.
_REQUIRE_TYPE = re.compile(r"^(\s*)type\?: (Type\d*);$", flags=re.MULTILINE)

ALIAS_FOOTER = """
// Python type aliases that pydantic2ts loses (it names types by field path).
export type TriageState = PredictedTriageState;
export type TriageReason = PredictedTriageReasons[number];
"""


def _post_process(text: str) -> str:
    return _REQUIRE_TYPE.sub(r"\1type: \2;", text) + ALIAS_FOOTER

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the generated file is out of date (CI guard).",
    )
    args = parser.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "pydantic2ts",
        "--module",
        "backend.app.domain.models",
        "--output",
        str(OUT),
    ]

    if args.check:

        tmp = OUT.with_suffix(".ts.check")
        cmd[-1] = str(tmp)
        subprocess.run(cmd, check=True, cwd=ROOT)
        tmp.write_text(_post_process(tmp.read_text()))
        if not OUT.exists() or OUT.read_bytes() != tmp.read_bytes():
            tmp.unlink(missing_ok=True)
            print("ERROR: generated types are out of date. Run scripts/generate_types.py.")
            return 1
        tmp.unlink(missing_ok=True)
        return 0

    subprocess.run(cmd, check=True, cwd=ROOT)
    OUT.write_text(_post_process(OUT.read_text()))
    print(f"Wrote {OUT.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
