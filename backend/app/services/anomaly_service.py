from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.adapters.storage import anomaly_repo
from app.db.models import AnomalyAck, Extraction, Invoice, User, Vendor
from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyAggregates,
    AnomalyCounts,
    AnomalyHistoryPoint,
    AnomalyMetric,
    AnomalyOut,
    BulkAcknowledgeFailure,
    BulkAcknowledgeOut,
)

SUPPORTED_SUBTYPE = "amount"
SUPPORTED_FIELD = "total"
HISTORY_LIMIT = 11


def list_anomalies(session: Session) -> AnomaliesResponse:
    rows = session.execute(
        select(Invoice, Extraction, Vendor)
        .join(Extraction, Extraction.invoice_id == Invoice.id)
        .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
        .where(Extraction.is_current.is_(True))
    ).all()

    invoice_ids = [inv.id for inv, _, _ in rows]
    acks = {
        (ack.invoice_id, ack.anomaly_subtype, ack.anomaly_field): ack
        for ack in anomaly_repo.list_acks_by_invoice_ids(session, invoice_ids=invoice_ids)
    }

    ack_users = _load_ack_users(session, acks)

    anomalies: list[AnomalyOut] = []
    for inv, extr, vendor in rows:
        if vendor is None:
            continue
        for reason in extr.predicted_triage_reasons or []:
            if reason.get("type") != "anomaly":
                continue
            field = reason.get("field")
            if field != SUPPORTED_FIELD:
                continue
            anomaly = _build_anomaly_out(
                session=session,
                invoice=inv,
                extraction=extr,
                vendor=vendor,
                reason=reason,
                ack=acks.get((inv.id, SUPPORTED_SUBTYPE, field)),
                ack_user_email=_email_for_ack(acks.get((inv.id, SUPPORTED_SUBTYPE, field)), ack_users),
            )
            anomalies.append(anomaly)

    anomalies.sort(key=lambda a: a.detected_at, reverse=True)
    counts = _compute_counts(anomalies)
    aggregates = _compute_aggregates(anomalies)
    return AnomaliesResponse(anomalies=anomalies, counts=counts, aggregates=aggregates)


def _build_anomaly_out(
    *,
    session: Session,
    invoice: Invoice,
    extraction: Extraction,
    vendor: Vendor,
    reason: dict[str, Any],
    ack: AnomalyAck | None,
    ack_user_email: str | None,
) -> AnomalyOut:
    fields = extraction.extracted_fields or {}
    total_spec = fields.get(SUPPORTED_FIELD) or {}
    value = float(total_spec.get("value") or 0.0)
    currency_spec = fields.get("currency") or {}
    currency = str(currency_spec.get("value") or "USD")
    z = float(reason.get("z_score") or 0.0)
    avg = float(reason.get("vendor_mean") or 0.0)

    prior = anomaly_repo.vendor_history_query(
        session,
        vendor_id=vendor.id,
        exclude_invoice_id=invoice.id,
        limit=HISTORY_LIMIT,
    )
    history = [AnomalyHistoryPoint(value=v) for v in reversed(prior)]
    history.append(AnomalyHistoryPoint(value=value, current=True))

    return AnomalyOut(
        id=f"{invoice.id}:{SUPPORTED_SUBTYPE}:{SUPPORTED_FIELD}",
        type="amount",
        status="acknowledged" if ack else "unreviewed",
        vendor=vendor.name,
        invoice_id=invoice.id,
        detected_at=invoice.uploaded_at,
        headline=_format_headline(value, currency),
        sub=_format_sub(z, avg, currency),
        z_score=z,
        severity=_severity_band(z),
        metric=AnomalyMetric(value=value, currency=currency, unit="$"),
        history=history,
        avg=avg,
        acknowledged_at=ack.acknowledged_at if ack else None,
        acknowledged_by=ack_user_email,
    )


def _format_headline(value: float, currency: str) -> str:
    if currency == "USD":
        return f"${value:,.2f} invoice"
    return f"{currency} {value:,.2f} invoice"


def _format_sub(z: float, avg: float, currency: str) -> str:
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{z:.1f}σ above rolling average of {symbol}{avg:,.0f}"


def _severity_band(z: float) -> str:
    if z >= 4.0:
        return "high"
    if z >= 2.5:
        return "medium"
    return "low"


def _compute_counts(anomalies: list[AnomalyOut]) -> AnomalyCounts:
    unreviewed = [a for a in anomalies if a.status == "unreviewed"]
    acked = [a for a in anomalies if a.status == "acknowledged"]
    return AnomalyCounts(
        all=len(anomalies),
        unreviewed=len(unreviewed),
        amount=len([a for a in unreviewed if a.type == "amount"]),
        frequency=0,
        pattern=0,
        acknowledged=len(acked),
    )


def _compute_aggregates(anomalies: list[AnomalyOut]) -> AnomalyAggregates:
    unreviewed = [a for a in anomalies if a.status == "unreviewed"]
    if not unreviewed:
        return AnomalyAggregates(
            total_flagged_amount=0.0,
            total_flagged_currency="USD",
            vendors_affected=0,
            highest_severity_z=None,
            highest_severity_vendor=None,
        )

    buckets: dict[str, float] = defaultdict(float)
    for a in unreviewed:
        buckets[a.metric.currency] += a.metric.value
    dominant = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    top = max(unreviewed, key=lambda a: a.z_score)
    return AnomalyAggregates(
        total_flagged_amount=round(dominant[1], 2),
        total_flagged_currency=dominant[0],
        vendors_affected=len({a.vendor for a in unreviewed}),
        highest_severity_z=top.z_score,
        highest_severity_vendor=top.vendor,
    )


def _load_ack_users(
    session: Session, acks: dict[tuple, AnomalyAck]
) -> dict[UUID, str]:
    user_ids = {ack.acknowledged_by_user_id for ack in acks.values()}
    if not user_ids:
        return {}
    rows = session.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
    return {u.id: str(u.email) for u in rows}


def _email_for_ack(ack: AnomalyAck | None, users: dict[UUID, str]) -> str | None:
    if ack is None:
        return None
    return users.get(ack.acknowledged_by_user_id)


def parse_anomaly_id(anomaly_id: str) -> tuple[UUID, str, str]:
    parts = anomaly_id.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"malformed anomaly id: {anomaly_id!r}")
    invoice_id_raw, subtype, field = parts
    try:
        invoice_id = UUID(invoice_id_raw)
    except ValueError as exc:
        raise ValueError(f"invalid invoice id in anomaly id: {anomaly_id!r}") from exc
    if subtype != SUPPORTED_SUBTYPE:
        raise ValueError(f"unsupported anomaly subtype: {subtype!r}")
    return invoice_id, subtype, field


def acknowledge(
    session: Session,
    *,
    anomaly_id: str,
    user_id: UUID,
    notes: str | None,
) -> AnomalyOut:
    invoice_id, subtype, field = parse_anomaly_id(anomaly_id)

    row = session.execute(
        select(Invoice, Extraction, Vendor)
        .join(Extraction, Extraction.invoice_id == Invoice.id)
        .join(Vendor, Vendor.id == Invoice.vendor_id, isouter=True)
        .where(
            Invoice.id == invoice_id,
            Extraction.is_current.is_(True),
        )
    ).first()
    if row is None or row[2] is None:
        raise LookupError(f"no active anomaly for id {anomaly_id!r}")

    invoice, extraction, vendor = row
    reason = next(
        (
            r
            for r in (extraction.predicted_triage_reasons or [])
            if r.get("type") == "anomaly" and r.get("field") == field
        ),
        None,
    )
    if reason is None:
        raise LookupError(f"no anomaly reason for id {anomaly_id!r}")

    ack = anomaly_repo.create_ack(
        session,
        invoice_id=invoice_id,
        subtype=subtype,
        field=field,
        user_id=user_id,
        notes=notes,
    )

    fields = extraction.extracted_fields or {}
    value = float((fields.get(field) or {}).get("value") or 0.0)
    _append_acknowledged_outlier(
        session=session,
        vendor=vendor,
        field=field,
        value=value,
        invoice_id=invoice_id,
        acked_at=ack.acknowledged_at,
    )

    user_email = session.execute(
        select(User.email).where(User.id == user_id)
    ).scalar_one()

    return _build_anomaly_out(
        session=session,
        invoice=invoice,
        extraction=extraction,
        vendor=vendor,
        reason=reason,
        ack=ack,
        ack_user_email=str(user_email),
    )


def acknowledge_bulk(
    session: Session,
    *,
    anomaly_ids: list[str],
    user_id: UUID,
) -> BulkAcknowledgeOut:
    acknowledged: list[AnomalyOut] = []
    failed: list[BulkAcknowledgeFailure] = []
    for aid in anomaly_ids:
        try:
            anomaly = acknowledge(session, anomaly_id=aid, user_id=user_id, notes=None)
            acknowledged.append(anomaly)
        except LookupError:
            failed.append(BulkAcknowledgeFailure(id=aid, error="not_found"))
        except ValueError as exc:
            failed.append(BulkAcknowledgeFailure(id=aid, error=str(exc)))
    return BulkAcknowledgeOut(acknowledged=acknowledged, failed=failed)


def _append_acknowledged_outlier(
    *,
    session: Session,
    vendor: Vendor,
    field: str,
    value: float,
    invoice_id: UUID,
    acked_at: datetime,
) -> None:
    memory = dict(vendor.memory or {})
    outliers = dict(memory.get("acknowledged_outliers", {}) or {})
    field_list = list(outliers.get(field, []) or [])

    already = any(
        abs(value - float(o.get("value") or 0.0)) < 1e-6 for o in field_list
    )
    if not already:
        field_list.append(
            {
                "value": value,
                "acked_at": acked_at.astimezone(UTC).isoformat(),
                "invoice_id": str(invoice_id),
            }
        )

    outliers[field] = field_list
    memory["acknowledged_outliers"] = outliers
    vendor.memory = memory
    flag_modified(vendor, "memory")
    session.commit()
