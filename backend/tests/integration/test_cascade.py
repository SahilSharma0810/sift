"""Cascade orchestration tests per ADR-0003.

These tests cover the cascade module in isolation - no real LLM, no DB.
They drive a stub LLMClient through scripted Haiku/Sonnet/Opus responses
and assert the resulting CascadeResult (final fields, agreement overrides,
trace, per-field source).

Parity with the pre-refactor `_run_cascade` is checked by the
test_extraction_service.py integration suite, which exercises the cascade
end-to-end via extract_from_pdf.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.adapters.llm_client import ExtractionResult
from app.config import Settings
from app.services.cascade import CascadeResult, run_cascade


def _result(
    *,
    fields: dict[str, Any] | None = None,
    self_conf: dict[str, float] | None = None,
    model: str = "claude-haiku-4-5",
    extraction_failed: bool = False,
) -> ExtractionResult:
    return ExtractionResult(
        fields=fields or {},
        self_reported_confidence=self_conf or {},
        extraction_failed=extraction_failed,
        extraction_failure_reason=None,
        model=model,
        prompt_hash="ph",
        schema_hash="sh",
        usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )


CONFIDENT_FIELDS = {
    "vendor_name": "Vega Logistics",
    "invoice_number": "INV-2026-0042",
    "invoice_date": "2026-05-13",
    "subtotal": 1000.0,
    "tax": 180.0,
    "total": 1180.0,
    "currency": "USD",
}


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def stub_llm() -> MagicMock:
    return MagicMock()


class TestNoFire:
    def test_no_fire_returns_single_tier_result(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Confident composite + math passed + known vendor -> no escalation."""
        initial = _result(fields=CONFIDENT_FIELDS)

        result = run_cascade(
            llm=stub_llm,
            initial=initial,
            initial_tier="haiku",
            invoice_text="...",
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.95, "vendor_name": 0.9},
            math_passed=True,
            is_unseen_vendor=False,
        )

        assert result.cascade_fired is False
        assert len(result.tier_traces) == 1
        assert result.tier_traces[0].model == "claude-haiku-4-5"
        assert result.final_fields["total"] == 1180.0
        assert result.agreement_overrides == {}
        assert all(s == "haiku" for s in result.per_field_source.values())
        stub_llm.call.assert_not_called()


class TestHaikuToSonnet:
    def test_agreement_no_escalation_to_opus(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Haiku and Sonnet agree on everything -> Sonnet trace appended, no Opus."""
        haiku = _result(fields=CONFIDENT_FIELDS, model="claude-haiku-4-5")
        sonnet = _result(fields=CONFIDENT_FIELDS, model="claude-sonnet-4-6")
        stub_llm.call.return_value = sonnet

        result = run_cascade(
            llm=stub_llm,
            initial=haiku,
            initial_tier="haiku",
            invoice_text="invoice text...",
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.5},  # forces trigger
            math_passed=True,
            is_unseen_vendor=False,
        )

        assert result.cascade_fired is True
        assert len(result.tier_traces) == 2
        assert result.tier_traces[1].model == "claude-sonnet-4-6"
        # All agreement scores 1.0 -> no field disputed, source stays Haiku.
        assert all(s == 1.0 for s in result.agreement_overrides.values())
        assert all(src == "haiku" for src in result.per_field_source.values())
        stub_llm.call.assert_called_once()

    def test_dispute_on_total_escalates_to_opus_and_opus_wins(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Haiku says $1180, Sonnet says $1200 (dispute), Opus says $1200."""
        haiku = _result(fields={**CONFIDENT_FIELDS, "total": 1180.0})
        sonnet_fields = {**CONFIDENT_FIELDS, "total": 1200.0, "tax": 200.0}
        opus_fields = {**CONFIDENT_FIELDS, "total": 1200.0, "tax": 200.0}
        sonnet = _result(fields=sonnet_fields, model="claude-sonnet-4-6")
        opus = _result(fields=opus_fields, model="claude-opus-4-7")
        stub_llm.call.side_effect = [sonnet, opus]

        result = run_cascade(
            llm=stub_llm,
            initial=haiku,
            initial_tier="haiku",
            invoice_text="...",
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.5},
            math_passed=True,
            is_unseen_vendor=False,
        )

        assert result.cascade_fired is True
        assert len(result.tier_traces) == 3
        assert result.final_fields["total"] == 1200.0
        assert result.per_field_source["total"] == "opus"
        # Two-of-three consensus: Sonnet's value matched Opus -> dispute lifted to 1.0.
        assert result.agreement_overrides["total"] == 1.0


class TestSameErrorBlindSpot:
    def test_math_fail_after_sonnet_forces_total_to_opus(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Both Haiku and Sonnet agree on `total` but math doesn't reconcile.
        ADR-0003 same-error blind spot: force `total` to Opus."""
        # Haiku and Sonnet both say total=$1200 but subtotal+tax=$1180. Math fails.
        broken_math = {**CONFIDENT_FIELDS, "total": 1200.0}  # 1000 + 180 != 1200
        haiku = _result(fields=broken_math, model="claude-haiku-4-5")
        sonnet = _result(fields=broken_math, model="claude-sonnet-4-6")
        # Opus catches the right total ($1180).
        opus_fields = {**CONFIDENT_FIELDS, "total": 1180.0}
        opus = _result(fields=opus_fields, model="claude-opus-4-7")
        stub_llm.call.side_effect = [sonnet, opus]

        result = run_cascade(
            llm=stub_llm,
            initial=haiku,
            initial_tier="haiku",
            invoice_text="...",
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.5},
            math_passed=False,  # Haiku already failed math
            is_unseen_vendor=False,
        )

        assert result.cascade_fired is True
        assert len(result.tier_traces) == 3  # Opus ran despite Haiku=Sonnet agreement
        assert result.final_fields["total"] == 1180.0
        assert result.per_field_source["total"] == "opus"


class TestVisionPath:
    def test_vision_no_inner_trigger_skips_opus(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Vision Sonnet with passing math + high self-confidence ->
        outer cascade fires (unseen vendor) but inner trigger says skip Opus."""
        initial = _result(
            fields=CONFIDENT_FIELDS,
            self_conf={k: 0.95 for k in CONFIDENT_FIELDS},
            model="claude-sonnet-4-6",
        )

        result = run_cascade(
            llm=stub_llm,
            initial=initial,
            initial_tier="sonnet",
            invoice_text=None,
            page_pngs=[b"\x89PNG..."],
            settings=settings,
            composite_confidence={"total": 0.85},
            math_passed=True,
            is_unseen_vendor=True,  # outer trigger ON
        )

        assert result.cascade_fired is False
        assert len(result.tier_traces) == 1
        stub_llm.call.assert_not_called()

    def test_vision_low_self_confidence_escalates_to_opus(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Vision Sonnet reports low self-conf on required field -> Opus runs."""
        low_self_conf = _result(
            fields=CONFIDENT_FIELDS,
            self_conf={"total": 0.5, "vendor_name": 0.95},
            model="claude-sonnet-4-6",
        )
        opus = _result(fields=CONFIDENT_FIELDS, model="claude-opus-4-7")
        stub_llm.call.return_value = opus

        result = run_cascade(
            llm=stub_llm,
            initial=low_self_conf,
            initial_tier="sonnet",
            invoice_text=None,
            page_pngs=[b"\x89PNG..."],
            settings=settings,
            composite_confidence={"total": 0.5},
            math_passed=True,
            is_unseen_vendor=False,
        )

        assert result.cascade_fired is True
        assert len(result.tier_traces) == 2
        stub_llm.call.assert_called_once()


class TestForceEscalate:
    def test_force_escalate_on_confident_initial_still_runs_cascade(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Clerk forces Sonnet on a digital invoice the auto-pipeline would
        consider confident. Cascade module runs anyway and adds Opus
        agreement-scoring discipline - same quality posture as auto-cascade."""
        # initial_tier="sonnet" means the initial extraction was already at Sonnet
        # (force_tier="sonnet" on the digital path). Cascade now compares to Opus.
        sonnet_initial = _result(fields=CONFIDENT_FIELDS, model="claude-sonnet-4-6")
        opus = _result(fields=CONFIDENT_FIELDS, model="claude-opus-4-7")
        stub_llm.call.return_value = opus

        result = run_cascade(
            llm=stub_llm,
            initial=sonnet_initial,
            initial_tier="sonnet",
            invoice_text="...",  # digital path
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.95},  # would NOT fire auto-trigger
            math_passed=True,
            is_unseen_vendor=False,
            force_escalate=True,
        )

        assert result.cascade_fired is True
        assert len(result.tier_traces) == 2
        stub_llm.call.assert_called_once()

    def test_force_escalate_at_top_tier_returns_base(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """Clerk forces Opus - no higher tier exists. Single-tier result."""
        opus_initial = _result(fields=CONFIDENT_FIELDS, model="claude-opus-4-7")

        result = run_cascade(
            llm=stub_llm,
            initial=opus_initial,
            initial_tier="opus",
            invoice_text="...",
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
            force_escalate=True,
        )

        assert result.cascade_fired is False
        assert len(result.tier_traces) == 1
        stub_llm.call.assert_not_called()


class TestCascadeResultShape:
    def test_trace_tiers_dicts_round_trip(
        self, stub_llm: MagicMock, settings: Settings
    ) -> None:
        """The persistable shape of tier_traces (dicts) preserves all fields
        that the on-disk cascade_trace.tiers JSONB column expects."""
        initial = _result(fields=CONFIDENT_FIELDS)
        result: CascadeResult = run_cascade(
            llm=stub_llm,
            initial=initial,
            initial_tier="haiku",
            invoice_text=None,
            page_pngs=None,
            settings=settings,
            composite_confidence={"total": 0.95},
            math_passed=True,
            is_unseen_vendor=False,
        )

        dicts = result.trace_tiers_dicts
        assert len(dicts) == 1
        assert set(dicts[0].keys()) == {
            "model",
            "prompt_hash",
            "schema_hash",
            "usage",
            "llm_self_confidence",
        }
