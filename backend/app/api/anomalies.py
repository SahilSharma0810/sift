from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_clerk
from app.db.session import get_session
from app.domain.anomalies_models import (
    AnomaliesResponse,
    AnomalyOut,
    BulkAcknowledgeIn,
    BulkAcknowledgeOut,
)
from app.domain.auth import ClerkOut
from app.services import anomaly_service

router = APIRouter()


@router.get("", response_model=AnomaliesResponse)
def list_anomalies_endpoint(
    _clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> AnomaliesResponse:
    return anomaly_service.list_anomalies(session)


@router.post("/{anomaly_id}/acknowledge", response_model=AnomalyOut)
def acknowledge_endpoint(
    anomaly_id: str,
    clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> AnomalyOut:
    try:
        return anomaly_service.acknowledge(
            session,
            anomaly_id=anomaly_id,
            user_id=clerk.id,
            notes=None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post("/acknowledge-bulk", response_model=BulkAcknowledgeOut)
def acknowledge_bulk_endpoint(
    body: BulkAcknowledgeIn,
    clerk: ClerkOut = Depends(get_current_clerk),
    session: Session = Depends(get_session),
) -> BulkAcknowledgeOut:
    return anomaly_service.acknowledge_bulk(
        session,
        anomaly_ids=body.anomaly_ids,
        user_id=clerk.id,
    )
