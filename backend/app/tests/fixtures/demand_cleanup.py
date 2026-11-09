"""Remove messages owned by test agents, including generated checks and summaries."""
from sqlalchemy import delete, or_, select, update

from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.db.models.moodle_approval import MoodleApproval


async def cleanup_agent_demands(db, agent_ids):
    ids = list((await db.scalars(select(AgentDemand.id).where(or_(
        AgentDemand.from_agent_id.in_(agent_ids),
        AgentDemand.target_agent_id.in_(agent_ids),
        AgentDemand.incubation_owner_id.in_(agent_ids),
    )))).all())
    if not ids:
        return
    await db.execute(delete(MoodleApproval).where(MoodleApproval.message_id.in_(ids)))
    await db.execute(delete(Notification).where(or_(
        *(Notification.event_key.contains(str(demand_id)) for demand_id in ids),
    )))
    await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
    # Both references use RESTRICT. Unlink only edges within this fixture's
    # records before deleting the set; outside references still prevent deletion.
    for reference in (AgentDemand.failure_check_source_id, AgentDemand.consolidated_into_id):
        await db.execute(update(AgentDemand).where(
            AgentDemand.id.in_(ids), reference.in_(ids),
        ).values({reference: None}))
    await db.execute(delete(AgentDemand).where(AgentDemand.id.in_(ids)))
