"""Adapter layer — IO seams.

The ONLY modules that talk outside the process. LLM client, PDF reader,
repositories. Adapters import from domain (for types only) — never from
services.
"""
