"""Test fixture seed — 5 invoices for tests/integration/.

Smallest set that exercises all four predicted_triage_state values
(confident, needs_review, likely_duplicate) plus an unprocessable
review_status per ADR-0006.
"""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("seed_minimal.py lands with tests/integration/ fixtures.")


if __name__ == "__main__":
    main()
