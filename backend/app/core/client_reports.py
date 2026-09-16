"""Create immutable, escaped client report snapshots from observed data."""
import calendar
import html
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.client_report import ClientReport
from app.db.models.governance import AuditEvent

logger = logging.getLogger(__name__)
UNAVAILABLE_HOURS = "Dados de atendimentos e horas não disponíveis nesta fonte"


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _text(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _render(snapshot: dict) -> str:
    client = snapshot["client"]
    stations = snapshot["workstations"]
    issues = snapshot["irregularities"]
    rows = "".join(
        f"<tr><td>{_text(item['hostname'])}</td><td>{_text(item['os_kind'])}</td>"
        f"<td>{_text(item['last_report_at'] or 'Sem relatório')}</td></tr>"
        for item in stations
    ) or "<tr><td colspan='3'>Nenhuma estação observada</td></tr>"
    issue_rows = "".join(
        f"<tr><td>{_text(item['hostname'])}</td><td>{_text(item['rule_key'])}</td>"
        f"<td>{_text(item['severity'])}</td><td>{_text(item['detail'])}</td>"
        f"<td>{_text(item['status'])}</td></tr>"
        for item in issues
    ) or "<tr><td colspan='5'>Nenhuma ocorrência no período</td></tr>"
    open_count = sum(item["status"] != "resolved" for item in issues)
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Relatório de acompanhamento</title>"
        "<style>body{font:16px system-ui;max-width:900px;margin:2rem auto;color:#17212b}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid #ccd5dd;padding:.5rem;text-align:left}"
        "@media print{body{margin:0}}</style></head><body>"
        f"<h1>Relatório de acompanhamento — {_text(client['name'])}</h1>"
        f"<p>Período: {_text(snapshot['period_start'])} a {_text(snapshot['period_end'])} (UTC)</p>"
        f"<p>Gerado em {_text(snapshot['generated_at'])}</p>"
        "<h2>Resumo</h2>"
        f"<p>{len(stations)} estações observadas; {len(issues)} ocorrências no período.</p>"
        "<h2>Estações</h2><p>Estado observado na geração; o histórico de inventário não está disponível.</p>"
        "<table><thead><tr><th>Hostname</th><th>Sistema</th><th>Último relatório</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<h2>Ocorrências</h2><table><thead><tr><th>Estação</th><th>Regra</th><th>Severidade</th>"
        f"<th>Detalhe</th><th>Estado</th></tr></thead><tbody>{issue_rows}</tbody></table>"
        "<h2>Alterações observáveis</h2><p>As ocorrências acima mostram o estado conhecido na geração. "
        "Esta fonte não mantém um histórico completo das alterações.</p>"
        f"<h2>Riscos</h2><p>{open_count} ocorrências não resolvidas na geração.</p>"
        "<h2>Pendências</h2><p>Consultar as ocorrências não resolvidas acima.</p>"
        f"<h2>Horas e saldo</h2><p>{UNAVAILABLE_HOURS}</p>"
        "</body></html>"
    )


async def generate_client_report(
    db: AsyncSession,
    client_id: uuid.UUID,
    period_start: date,
    period_end: date,
    *,
    kind: str,
    irregularity_id: uuid.UUID | None = None,
    generated_by_user_id: uuid.UUID | None = None,
) -> ClientReport:
    if period_end < period_start or period_end == date.max:
        raise HTTPException(422, "Invalid report interval")
    if kind not in {"monthly", "on_demand"}:
        raise HTTPException(422, "Invalid report kind")
    if kind == "monthly" and (
        period_start.day != 1
        or period_start.year != period_end.year
        or period_start.month != period_end.month
        or period_end.day != calendar.monthrange(period_start.year, period_start.month)[1]
        or irregularity_id is not None
    ):
        raise HTTPException(422, "Monthly reports require a complete month")
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    if kind == "monthly":
        existing = (await db.execute(select(ClientReport).where(
            ClientReport.client_id == client_id, ClientReport.period_start == period_start,
            ClientReport.kind == "monthly",
        ))).scalar_one_or_none()
        if existing is not None:
            return existing

    workstations = list((await db.execute(select(Workstation).where(
        Workstation.client_id == client_id
    ).order_by(Workstation.hostname, Workstation.id))).scalars())
    station_by_id = {row.id: row for row in workstations}
    if irregularity_id is not None:
        chosen = await db.get(Irregularity, irregularity_id)
        if chosen is None or chosen.workstation_id not in station_by_id:
            raise HTTPException(404, "Irregularity not found")
    start_utc = datetime.combine(period_start, time.min, timezone.utc)
    end_exclusive = datetime.combine(period_end + timedelta(days=1), time.min, timezone.utc)
    query = select(Irregularity).join(Workstation, Workstation.id == Irregularity.workstation_id).where(
        Workstation.client_id == client_id,
        Irregularity.detected_at < end_exclusive,
        (Irregularity.resolved_at.is_(None) | (Irregularity.resolved_at >= start_utc)),
    ).order_by(Irregularity.detected_at, Irregularity.id)
    if irregularity_id is not None:
        query = query.where(Irregularity.id == irregularity_id)
    issues = list((await db.execute(query)).scalars())
    generated_at = datetime.now(timezone.utc)
    snapshot = {
        "client": {"id": str(client.id), "name": client.name},
        "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
        "generated_at": _utc(generated_at),
        "inventory_note": "Estado observado na geração",
        "hours_note": UNAVAILABLE_HOURS,
        "workstations": [{
            "id": str(row.id), "hostname": row.hostname, "os_kind": row.os_kind,
            "last_report_at": _utc(row.last_report_at), "last_seen_agent_version": row.last_seen_agent_version,
        } for row in workstations],
        "irregularities": [{
            "id": str(row.id), "workstation_id": str(row.workstation_id),
            "hostname": station_by_id[row.workstation_id].hostname,
            "rule_key": row.rule_key, "severity": row.severity, "detail": row.detail,
            "status": row.status, "detected_at": _utc(row.detected_at), "resolved_at": _utc(row.resolved_at),
        } for row in issues],
    }
    html_content = _render(snapshot)
    if kind == "monthly":
        report_id = uuid.uuid4()
        statement = insert(ClientReport).values(
            id=report_id, client_id=client_id, kind=kind, period_start=period_start,
            period_end=period_end, irregularity_id=irregularity_id, snapshot=snapshot,
            html_content=html_content, generated_at=generated_at,
            generated_by_user_id=generated_by_user_id,
        ).on_conflict_do_nothing(index_elements=["client_id", "period_start"], index_where=ClientReport.kind == "monthly").returning(ClientReport.id)
        inserted_id = (await db.execute(statement)).scalar_one_or_none()
        if inserted_id is None:
            return (await db.execute(select(ClientReport).where(
                ClientReport.client_id == client_id, ClientReport.period_start == period_start,
                ClientReport.kind == "monthly",
            ))).scalar_one()
        report = await db.get(ClientReport, inserted_id)
    else:
        report = ClientReport(
            client_id=client_id, kind=kind, period_start=period_start,
            period_end=period_end, irregularity_id=irregularity_id, snapshot=snapshot,
            html_content=html_content, generated_at=generated_at,
            generated_by_user_id=generated_by_user_id,
        )
        db.add(report)
        await db.flush()
    db.add(AuditEvent(
        entity_type="client_report", entity_id=report.id, event_type="generated",
        actor=str(generated_by_user_id) if generated_by_user_id else "system",
        payload={"client_id": str(client_id), "kind": kind,
                 "period_start": period_start.isoformat(), "period_end": period_end.isoformat()},
    ))
    await db.flush()
    return report


async def run_monthly_report_pass(db_factory, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    month_end = current.date().replace(day=1) - timedelta(days=1)
    month_start = month_end.replace(day=1)
    cutoff = datetime.combine(month_end + timedelta(days=1), time.min, timezone.utc)
    async with db_factory() as db:
        client_ids = list((await db.execute(select(Client.id).where(Client.created_at < cutoff))).scalars())
    created = 0
    for client_id in client_ids:
        try:
            async with db_factory() as db:
                existed = (await db.execute(select(ClientReport.id).where(
                    ClientReport.client_id == client_id,
                    ClientReport.period_start == month_start,
                    ClientReport.kind == "monthly",
                ))).scalar_one_or_none()
                if existed is None:
                    await generate_client_report(db, client_id, month_start, month_end, kind="monthly")
                    await db.commit()
                    created += 1
        except Exception:
            logger.exception("Monthly report generation failed for client %s", client_id)
    return created
