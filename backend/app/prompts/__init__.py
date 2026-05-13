"""Versioned prompt loader per ADR-0005 rule 3.

Content-hashed at startup; the hash is included in every LLM call log so
EVAL.md numbers correlate to specific prompt versions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
SCHEMA_DIR = PROMPT_DIR / "schemas"


@dataclass(frozen=True, slots=True)
class LoadedPrompt:
    name: str
    body: str
    body_hash: str
    schema: dict
    schema_hash: str


def _hash(s: str | bytes) -> str:
    data = s.encode() if isinstance(s, str) else s
    return hashlib.sha256(data).hexdigest()[:16]


@lru_cache(maxsize=8)
def load(name: str) -> LoadedPrompt:
    """Load a versioned prompt + its tool-use schema.

    Example: load("extraction_header_v1") returns the prompt body and the
    extraction_header_schema.json contents (schema filename is canonical:
    `<base>_schema.json` where base strips the `_v\\d+` suffix).
    """
    prompt_path = PROMPT_DIR / f"{name}.md"
    body = prompt_path.read_text()

    base = name.rsplit("_v", 1)[0]
    schema_path = SCHEMA_DIR / f"{base}_schema.json"
    schema_text = schema_path.read_text()
    schema = json.loads(schema_text)

    return LoadedPrompt(
        name=name,
        body=body,
        body_hash=_hash(body),
        schema=schema,
        schema_hash=_hash(schema_text),
    )
