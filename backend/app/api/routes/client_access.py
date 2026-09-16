"""Tenant-scoped, credential-authenticated read API for client systems."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.client_report import _download
from app.api.schemas.client_report import ClientReportOut, ExternalIrregularityOut
from app.core.client_read_auth import get_client_read_credential
from app.db.base import get_db
from app.db.models.client import Irregularity, Workstation
from app.db.models.client_report import ClientReadCredential, ClientReport

router = APIRouter(prefix="/api/v1/client-access/clients", tags=["client-access"])


def _scope(client_id: uuid.UUID, credential: ClientReadCredential) -> None:
    if credential.client_id != client_id:
        raise HTTPException(404, "Client resource not found")


@router.get("/{client_id}/reports", response_model=list[ClientReportOut])
async def list_client_reports(client_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db), credential: ClientReadCredential = Depends(get_client_read_credential)):
    _scope(client_id, credential)
    return list((await db.execute(select(ClientReport).where(ClientReport.client_id == client_id, ClientReport.reviewed_at.is_not(None)).order_by(ClientReport.generated_at.desc(), ClientReport.id.desc()).limit(limit).offset(offset))).scalars())


@router.get("/{client_id}/reports/{report_id}/download")
async def download_client_report(client_id: uuid.UUID, report_id: uuid.UUID, db: AsyncSession = Depends(get_db), credential: ClientReadCredential = Depends(get_client_read_credential)):
    _scope(client_id, credential)
    report = (await db.execute(select(ClientReport).where(ClientReport.id == report_id, ClientReport.client_id == client_id, ClientReport.reviewed_at.is_not(None)))).scalar_one_or_none()
    if report is None:
        raise HTTPException(404, "Report not found")
    return _download(report)


@router.get("/{client_id}/irregularities", response_model=list[ExternalIrregularityOut])
async def list_client_irregularities(client_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: AsyncSession = Depends(get_db), credential: ClientReadCredential = Depends(get_client_read_credential)):
    _scope(client_id, credential)
    rows = (await db.execute(select(Irregularity, Workstation.hostname).join(Workstation, Workstation.id == Irregularity.workstation_id).where(Workstation.client_id == client_id).order_by(Irregularity.detected_at.desc(), Irregularity.id.desc()).limit(limit).offset(offset))).all()
    return [ExternalIrregularityOut(
        id=issue.id, workstation_id=issue.workstation_id, hostname=hostname,
        rule_key=issue.rule_key, severity=issue.severity, detail=issue.detail,
        status=issue.status, detected_at=issue.detected_at, resolved_at=issue.resolved_at,
    ) for issue, hostname in rows]
