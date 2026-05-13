"""API layer — thin route handlers.

Parse request → call one service method → serialize response. NO business
logic. Imports from services only. NEVER imports from adapters or db.
"""
