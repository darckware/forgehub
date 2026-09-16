"""Administrator-only report generation, review, download and credential issue."""
import calendar
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client_report import (
    ClientReportDetailOut, ClientReportOut, MonthlyReportCreate, ReadCredentialCreate,
    ReadCredentialIssued, ReadCredentialOut, ReportCreate, ReportReview,
)
from app.core.client_read_auth import hash_client_read_token, issue_client_read_token
from app.core.client_reports import generate_client_report
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Client
from app.db.models.client_report import ClientReadCredential, ClientReport
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1", tags=["client-reports"])


def _download(report: ClientReport) -> Response:
    return Response(
        content=report.html_content,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="client-report-{report.id}.html"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/clients/{client_id}/reports", response_model=list[ClientReportOut])
async def list_reports(client_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    if await db.get(Client, client_id) is None:
        raise HTTPException(404, "Client not found")
    return list((await db.execute(select(ClientReport).where(ClientReport.client_id == client_id).order_by(ClientReport.generated_at.desc(), ClientReport.id.desc()))).scalars())


@router.post("/clients/{client_id}/reports", response_model=ClientReportOut, status_code=201)
async def create_report(client_id: uuid.UUID, payload: ReportCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    report = await generate_client_report(db, client_id, payload.period_start, payload.period_end, kind="on_demand", irregularity_id=payload.irregularity_id, generated_by_user_id=admin.id)
    await db.commit()
    return report


@router.post("/clients/{client_id}/reports/monthly", response_model=ClientReportOut)
async def create_monthly_report(client_id: uuid.UUID, payload: MonthlyReportCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    year, month = map(int, payload.month.split("-"))
    if year < 1 or (year, month) >= (datetime.now(timezone.utc).year, datetime.now(timezone.utc).month):
        raise HTTPException(422, "Month must be closed")
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    report = await generate_client_report(db, client_id, start, end, kind="monthly", generated_by_user_id=admin.id)
    await db.commit()
    return report


@router.get("/client-reports/{report_id}", response_model=ClientReportDetailOut)
async def get_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    report = await db.get(ClientReport, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/client-reports/{report_id}/download")
async def download_report(report_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    report = await db.get(ClientReport, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return _download(report)


@router.patch("/client-reports/{report_id}/review", response_model=ClientReportOut)
async def review_report(report_id: uuid.UUID, payload: ReportReview, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    report = await db.get(ClientReport, report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    if payload.reviewed == (report.reviewed_at is not None):
        return report
    report.reviewed_at = datetime.now(timezone.utc) if payload.reviewed else None
    report.reviewed_by_user_id = admin.id if payload.reviewed else None
    db.add(AuditEvent(entity_type="client_report", entity_id=report.id,
                      event_type="reviewed" if payload.reviewed else "review_withdrawn",
                      actor=admin.username,
                      payload={"client_id": str(report.client_id), "period_start": report.period_start.isoformat(), "period_end": report.period_end.isoformat()}))
    await db.commit()
    await db.refresh(report)
    return report


@router.post("/clients/{client_id}/read-credentials", response_model=ReadCredentialIssued, status_code=201)
async def create_read_credential(client_id: uuid.UUID, payload: ReadCredentialCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    if await db.get(Client, client_id) is None:
        raise HTTPException(404, "Client not found")
    if payload.expires_at is not None and payload.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Expiry must be in the future")
    token = issue_client_read_token()
    credential = ClientReadCredential(client_id=client_id, token_hash=hash_client_read_token(token), expires_at=payload.expires_at, created_by_user_id=admin.id)
    db.add(credential)
    await db.flush()
    db.add(AuditEvent(entity_type="client_read_credential", entity_id=credential.id, event_type="issued", actor=admin.username, payload={"client_id": str(client_id)}))
    await db.commit()
    await db.refresh(credential)
    return ReadCredentialIssued(credential=ReadCredentialOut.model_validate(credential), token=token)


@router.get("/clients/{client_id}/read-credentials", response_model=list[ReadCredentialOut])
async def list_read_credentials(client_id: uuid.UUID, db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    if await db.get(Client, client_id) is None:
        raise HTTPException(404, "Client not found")
    return list((await db.execute(select(ClientReadCredential).where(ClientReadCredential.client_id == client_id).order_by(ClientReadCredential.created_at.desc()))).scalars())


@router.delete("/clients/{client_id}/read-credentials/{credential_id}", status_code=204)
async def revoke_read_credential(client_id: uuid.UUID, credential_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    credential = (await db.execute(select(ClientReadCredential).where(ClientReadCredential.id == credential_id, ClientReadCredential.client_id == client_id))).scalar_one_or_none()
    if credential is None:
        raise HTTPException(404, "Credential not found")
    if credential.revoked_at is None:
        credential.revoked_at = datetime.now(timezone.utc)
        db.add(AuditEvent(entity_type="client_read_credential", entity_id=credential.id, event_type="revoked", actor=admin.username, payload={"client_id": str(client_id)}))
        await db.commit()
    return Response(status_code=204)
