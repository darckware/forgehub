"""Monthly client report (client demands Onda 4, 2026-10-04).

Joins Darckware's cycle report (tickets, demands, hours against the support
quota) with this client's Software Factory projects (ForgeHub's own data), and
queues the result as an `informe_mensal` e-mail in Darckware's approval queue.
It is never sent from here: Marcelo approves it like any other e-mail.

Idempotent per client and cycle: the draft carries
`source_ref="monthly-report:<client>:<cycle start>"`, and a second run for the
same cycle returns the existing draft instead of queuing another one -- the
daily trigger can fire as often as it likes.

Plain text only, written to be read by the client: no internal ids, no agent
names, no hourly cost (the amount due is the contract's business, not this
report's).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import darckware_client as dw
from app.core.localtime import local_tz
from app.db.models.backlog import PlanningItem
from app.db.models.project import Project
from app.db.models.task import ProjectTask

_DONE_TASK = ("done", "deployed")
_PROJECT_STATUS_PT = {
    "planned": "planejado",
    "active": "em andamento",
    "on_hold": "pausado",
    "completed": "concluído",
    "cancelled": "cancelado",
}


def _br(d: str) -> str:
    return datetime.fromisoformat(d).strftime("%d/%m/%Y")


def _hours(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:g}".replace(".", ",") + " h"


async def client_projects_progress(db: AsyncSession, client_id: uuid.UUID) -> list[dict[str, Any]]:
    """This client's projects still worth reporting, with task progress."""
    rows = (
        await db.execute(
            select(
                Project.id,
                Project.name,
                Project.status,
                func.count(ProjectTask.id),
                func.count(case((ProjectTask.status.in_(_DONE_TASK), 1))),
            )
            .outerjoin(PlanningItem, PlanningItem.project_id == Project.id)
            .outerjoin(ProjectTask, ProjectTask.planning_item_id == PlanningItem.id)
            .where(Project.darckware_client_id == client_id, Project.status != "cancelled")
            .group_by(Project.id, Project.name, Project.status)
            .order_by(Project.name)
        )
    ).all()
    return [
        {"id": str(pid), "name": name, "status": status, "tasks_total": total, "tasks_done": done}
        for pid, name, status, total, done in rows
    ]


def _period(cycle: dict[str, Any], today: date) -> str:
    """Darckware's cycle ends on the next cut-off day itself; the client reads
    the day before it. A cycle still running is shown up to today, marked partial."""
    start = date.fromisoformat(cycle["start"])
    last = date.fromisoformat(cycle["end"]) - timedelta(days=1)
    if last >= today:
        return f"{start:%d/%m/%Y} a {today:%d/%m/%Y} (parcial)"
    return f"{start:%d/%m/%Y} a {last:%d/%m/%Y}"


def build_report_text(
    report: dict[str, Any], projects: list[dict[str, Any]], today: date | None = None
) -> tuple[str, str]:
    client = report["client"]
    period = _period(report["cycle"], today or datetime.now(local_tz()).date())
    first = (client.get("contact_name") or "").split(" ")[0] or "tudo bem"
    lines = [f"Olá, {first}!", "", f"Segue o resumo dos serviços da Darckware para {client['company_name']} no período de {period}.", ""]

    hours = report["hours"]
    if report.get("support_contract"):
        lines.append(f"Suporte ({report['support_contract']['plan_name']})")
        lines.append(f"- Horas utilizadas: {_hours(hours.get('used'))} de {_hours(hours.get('quota'))}")
        if hours.get("extra"):
            lines.append(f"- Horas excedentes: {_hours(hours['extra'])}")
        else:
            lines.append(f"- Saldo do período: {_hours(hours.get('remaining'))}")
        lines.append("")
    elif hours.get("used"):
        lines += [f"Horas de atendimento no período: {_hours(hours['used'])}", ""]

    entries = report.get("time_entries") or []
    if entries:
        lines.append("Atendimentos realizados")
        for e in entries:
            when = f"{_br(e['date'])} " if e.get("date") else ""
            lines.append(f"- {when}{e['description']} ({_hours(e['billable_hours'])})")
        lines.append("")

    def block(title: str, items: list[dict[str, Any]]) -> None:
        if items:
            lines.append(title)
            lines.extend(f"- {i['title']}" for i in items)
            lines.append("")

    tickets, demands = report["tickets"], report["demands"]
    block("Solicitações concluídas no período", tickets["closed"] + demands["closed"])
    block("Solicitações em aberto", tickets["open"] + demands["open"])

    if projects:
        lines.append("Projetos")
        for p in projects:
            status = _PROJECT_STATUS_PT.get(p["status"], p["status"])
            progress = f" — {p['tasks_done']} de {p['tasks_total']} etapas concluídas" if p["tasks_total"] else ""
            lines.append(f"- {p['name']}: {status}{progress}")
        lines.append("")

    if len(lines) <= 4:
        lines += ["Não houve chamados, atendimentos ou projetos registrados neste período.", ""]
    lines += [
        "O acompanhamento detalhado está no portal do cliente: https://darckware.net/cliente",
        "Qualquer dúvida, é só responder este e-mail.",
        "",
        "Lara",
        "Darckware",
    ]
    return f"Informe mensal Darckware — {client['company_name']} ({period})", "\n".join(lines)


async def generate_monthly_report(
    db: AsyncSession, client_id: uuid.UUID, *, actor: str, reference: date | None = None
) -> dict[str, Any]:
    """Queue (or find) the report draft for the cycle containing `reference`
    (default: yesterday -- the cycle that just closed on its cut-off day)."""
    if reference is None:
        reference = datetime.now(local_tz()).date() - timedelta(days=1)
    report = await dw.request("GET", f"/clients/{client_id}/cycle-report", params={"reference": reference.isoformat()})
    source_ref = f"monthly-report:{client_id}:{report['cycle']['start']}"
    existing = await dw.request("GET", "/outbound-emails", params={"source_ref": source_ref, "limit": 1})
    if existing.get("items"):
        return {"created": False, "email": existing["items"][0], "cycle": report["cycle"]}
    projects = await client_projects_progress(db, client_id)
    subject, body = build_report_text(report, projects)
    email = await dw.request(
        "POST",
        "/outbound-emails",
        json={
            "to_email": report["client"]["email"],
            "subject": subject,
            "body_text": body,
            "kind": "informe_mensal",
            "client_account_id": str(client_id),
            "source_system": "forgehub",
            "source_ref": source_ref,
            "created_by": actor,
        },
    )
    return {"created": True, "email": email, "cycle": report["cycle"]}


async def run_due_reports(db: AsyncSession, today: date | None = None) -> dict[str, Any]:
    """Daily trigger: every client whose cycle closes today gets its draft."""
    today = today or datetime.now(local_tz()).date()
    clients = (await dw.request("GET", "/clients-with-contracts")).get("items", [])
    due = [c for c in clients if int(c.get("billing_cycle_day") or 1) == today.day]
    results = []
    for c in due:
        try:
            r = await generate_monthly_report(
                db, uuid.UUID(c["id"]), actor="forgehub:monthly-report", reference=today - timedelta(days=1)
            )
            results.append({"client": c["company_name"], "created": r["created"], "email_id": r["email"]["id"]})
        except Exception as exc:  # one client's failure must not skip the others
            results.append({"client": c["company_name"], "error": str(getattr(exc, "detail", exc))})
    return {"date": today.isoformat(), "due": len(due), "results": results}
