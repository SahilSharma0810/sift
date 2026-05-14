"""NL → StructuredQuery translator (per ADR-0004).

Single seam between natural-language input and the downstream search
SQL builder. Calls the LLM adapter, validates the payload against the
Pydantic StructuredQuery model (FIELD_OP_COMPATIBILITY enforced there),
and raises a translator-specific error on malformed output so the API
layer can return a meaningful 422.

The same validation runs for both the stub and Anthropic providers — the
translator is the contract boundary, not the provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError

from app.adapters.llm_client import make_llm_client
from app.config import get_settings
from app.domain.nl_schema import StructuredQuery

if TYPE_CHECKING:
    from app.adapters.llm_client import LLMClient

log = structlog.get_logger(__name__)


class TranslationError(ValueError):
    """Raised when the LLM emits a payload that doesn't validate as a
    StructuredQuery. Carries the raw payload + the validation error so the
    API layer can return a useful 422.
    """

    def __init__(self, message: str, *, raw_payload: dict, errors: list[dict]) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload
        self.errors = errors


def translate(
    *,
    natural_language: str,
    llm: LLMClient | None = None,
) -> StructuredQuery:
    """Translate `natural_language` to a validated StructuredQuery.

    Raises TranslationError if the LLM emits a payload that doesn't
    validate. Whitespace-only input returns an empty StructuredQuery
    (no filters, no untranslated_intent) so the search page can render
    an unfiltered list rather than erroring.
    """
    settings = get_settings()
    if llm is None:
        llm = make_llm_client(settings)

    if not natural_language or not natural_language.strip():
        return StructuredQuery(filters=[], untranslated_intent=None)

    result = llm.extract_structured_query(
        natural_language=natural_language, model=settings.model_tier_2
    )

    try:
        query = StructuredQuery.model_validate(result.payload)
    except ValidationError as exc:
        log.warning(
            "nl_translation.invalid_payload",
            errors=exc.errors(),
            raw=result.payload,
        )
        raise TranslationError(
            "LLM produced a StructuredQuery payload that failed validation.",
            raw_payload=result.payload,
            errors=exc.errors(),
        ) from exc

    log.info(
        "nl_translation.done",
        n_filters=len(query.filters),
        untranslated=bool(query.untranslated_intent),
        model=result.model,
    )
    return query
