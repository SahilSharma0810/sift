"""Service layer — orchestration.

Imports from domain and adapters. NO HTTP, NO raw SQL.
One method per use case (extract_invoice, translate_nl_query,
bulk_confirm_invoices, retry_extraction, ...).
"""
