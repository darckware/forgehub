import pytest
from fastapi import HTTPException

from app.db.models.demand import AgentDemand


def test_approval_required_task_cannot_start_before_operator_decides():
    from app.core.demand_workflow import assert_execution_allowed

    demand = AgentDemand(origin_type="task", requires_approval=True, approval_status="pending")
    with pytest.raises(HTTPException) as error:
        assert_execution_allowed(demand)
    assert error.value.status_code == 409


def test_editing_approved_content_requires_a_new_decision():
    from app.core.demand_workflow import approval_fingerprint, assert_execution_allowed

    demand = AgentDemand(origin_type="task", body="Authorized work", requires_approval=True, approval_status="approved")
    demand.approved_content_hash = approval_fingerprint(demand)
    assert_execution_allowed(demand)
    demand.body = "Different work"
    with pytest.raises(HTTPException):
        assert_execution_allowed(demand)


def test_archived_or_consolidated_work_cannot_start():
    from app.core.demand_workflow import assert_execution_allowed

    with pytest.raises(HTTPException):
        assert_execution_allowed(AgentDemand(origin_type="task", status="archived"))
