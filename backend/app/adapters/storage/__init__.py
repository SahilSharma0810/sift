"""Storage adapters — SQLAlchemy-backed repositories.

One repo per aggregate root (invoices, extractions, vendors, corrections,
queries). Repos expose intention-revealing methods (save_for_eval, mark_current,
find_by_perceptual_hash) rather than generic ORM operations.
"""
