"""Security events for user access; never include credentials in payloads."""
import uuid

from app.core.agent_session import request_origin
from app.db.models.governance import AuditEvent


def record_user_event(db, event, actor, user_id, request, **details):
    db.add(AuditEvent(entity_type="user_access", entity_id=user_id or uuid.UUID(int=0),
                      event_type=event, actor=actor[:150],
                      payload={**request_origin(request), **details}))
