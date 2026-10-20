"""An atomic consolidation preserves source evidence and leaves a human decision pending."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand, INCUBATION_DEFAULT_MATURATION_DAYS
from app.db.models.governance import AuditEvent
from app.db.models.project import Project


async def consolidate_demands(db, payload, *, actor):
    sources = list((await db.execute(select(AgentDemand).where(
        AgentDemand.id.in_(payload.source_ids)
    ).order_by(AgentDemand.id).with_for_update())).scalars())
    if len(sources) != len(payload.source_ids):
        raise HTTPException(404, "One or more source messages no longer exist")
    existing = {source.consolidated_into_id for source in sources}
    if len(existing) == 1 and None not in existing:
        summary = await db.get(AgentDemand, next(iter(existing)))
        if summary.project_id != payload.project_id or summary.context_area != payload.context_area:
            raise HTTPException(409, "Sources already belong to another context")
        return summary
    for source in sources:
        if (source.status == "archived" or source.consolidated_into_id
            or source.dispatch_status in ("dispatched", "running")
            or (source.agent_run_id and source.dispatch_status is None)
            or not (source.dispatch_status == "failed" or source.origin_type == "incubation")
            or (source.project_id and source.project_id != payload.project_id)
            or (source.context_area and source.context_area != payload.context_area)):
            raise HTTPException(409, f"Source #{source.number} is active, archived, consolidated or belongs to another context")
    owner = await db.get(Agent, payload.owner_agent_id)
    if owner is None or not owner.is_active:
        raise HTTPException(400, "An active owner is required")
    if payload.project_id and await db.get(Project, payload.project_id) is None:
        raise HTTPException(404, "Project not found")
    references = []
    for source in sorted(sources, key=lambda row: row.number):
        uncertain = " — RECONCILIAÇÃO PENDENTE" if "uncertain" in (source.dispatch_error or "").lower() else ""
        references.append(f"- [#{source.number}](/demands?message={source.id}) — {source.subject}{uncertain}")
    summary = AgentDemand(
        from_agent=(owner.profile_slug or owner.name)[:50], from_agent_id=owner.id,
        target_agent_id=owner.id, incubation_owner_id=owner.id,
        subject=payload.subject, body=payload.body + "\n\n## Registros de origem\n" + "\n".join(references),
        origin_type="incubation", incubation_state="incubating", status="new",
        project_id=payload.project_id, context_area=payload.context_area,
        matures_at=datetime.now(timezone.utc) + timedelta(days=INCUBATION_DEFAULT_MATURATION_DAYS),
        requires_approval=True, approval_status="pending", working_path="/root/project/forgehub",
    )
    db.add(summary)
    await db.flush()
    for source in sources:
        source.consolidated_into_id = summary.id
        source.status = "archived"
        source.project_id = payload.project_id
        source.context_area = payload.context_area
    db.add(AuditEvent(entity_type="agent_demand", entity_id=summary.id, event_type="demand_consolidated",
        actor=actor, payload={"source_ids": [str(row.id) for row in sources], "source_numbers": [row.number for row in sources]}))
    await db.flush()
    return summary
