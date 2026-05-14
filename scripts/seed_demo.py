"""Demo seed — 25 beat-driven invoices per PLAN.md "Seed corpus".

Each slot has a documented role in the 60-second demo narrative. See the
slot table in PLAN.md. Pre-populates field_corrections + runs
vendor_memory_service.consolidate(...) so beat 3 has real history.

The Day-2.5 minimal version lives inside the backend container at
`backend/scripts/seed_demo.py` and is invoked via `make seed-demo`.
Day 5 expands it to the full 25-slot table.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError(
        "The runnable seed lives at backend/scripts/seed_demo.py. "
        "Run `make seed-demo`."
    )


if __name__ == "__main__":
    main()
