"""Independent, count-only operational checks. No I/O or remediation here.

SQL selects aggregate metadata in company only. The caller owns its read-only
psql transport; arbitrary row values and exception text never become evidence.
"""
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ModuleCheck:
    query: str
    fields: tuple[str, ...]
    violations: tuple[str, ...]
    minimum_registered: int = 0

    def evaluate(self, counts: Mapping[str, int]) -> tuple[bool, str]:
        if any(type(counts.get(key)) is not int or not 0 <= counts[key] <= 2**63 - 1 for key in self.fields):
            raise ValueError('Invalid aggregate metadata')
        healthy = not any(counts[key] for key in self.violations)
        if self.minimum_registered:
            healthy = healthy and counts['registered'] == self.minimum_registered
        return healthy, '; '.join(f'{key}={counts[key]}' for key in self.fields)


WORKER_QUERY = """
WITH expected(name, seconds) AS (VALUES ('scheduled-dispatch-poll',30),
 ('feedback-poll',120),('routine-poll',60),('mission-cycle-poll',60),('machine-status-poll',900)),
 observed AS (SELECT w.*, e.seconds FROM expected e
 JOIN company.operational_worker_observations w ON w.worker_name=e.name)
SELECT json_build_object('registered', count(*), 'disabled', count(*) FILTER (WHERE NOT enabled),
 'unhealthy', count(*) FILTER (WHERE
 interval_seconds <> seconds OR
 (NOT enabled AND last_status <> 'disabled') OR
 (enabled AND (last_status NOT IN ('ok','running') OR last_success_at IS NULL OR
 last_success_at > now() OR last_started_at > now() OR
 last_success_at < now()-make_interval(secs => greatest(seconds*2+120,180)) OR
 (last_status='running' AND last_started_at < now()-make_interval(secs => greatest(seconds*2+120,180)))))))
FROM observed
"""

MISSION_QUERY = """
WITH missions AS (SELECT m.*, p.status projection, p.project_type FROM company.project_missions m
 JOIN company.projects p ON p.id=m.project_id),
 issues AS (SELECT m.*,
 (m.project_type <> 'mission' OR m.projection <> CASE m.state
 WHEN 'draft' THEN 'planned' WHEN 'planning' THEN 'planned' WHEN 'ready' THEN 'planned'
 WHEN 'paused' THEN 'on_hold' WHEN 'completed' THEN 'completed' WHEN 'cancelled' THEN 'cancelled' ELSE 'active' END
 OR (m.state IN ('ready','active','verifying','awaiting_acceptance') AND NOT EXISTS (
 SELECT 1 FROM company.plan_baselines b JOIN company.project_plans p ON p.id=b.project_plan_id
 WHERE b.id=m.current_baseline_id AND p.project_id=m.project_id AND b.superseded_at IS NULL))
 OR (m.state NOT IN ('completed','cancelled') AND NOT EXISTS (
 SELECT 1 FROM company.project_agent_memberships pm JOIN company.agents a ON a.id=pm.agent_id
 WHERE pm.project_id=m.project_id AND pm.agent_id=m.orchestrator_agent_id
 AND pm.role='coordinator' AND pm.status='active' AND a.is_active
 AND (pm.valid_from IS NULL OR pm.valid_from<=current_date)
 AND (pm.valid_to IS NULL OR pm.valid_to>=current_date)))) invalid FROM missions m)
SELECT json_build_object('total',(SELECT count(*) FROM missions),
 'invalid',(SELECT count(*) FROM issues WHERE invalid),
 'missing_routine',(SELECT count(*) FROM missions m WHERE m.state IN ('planning','active','verifying')
 AND EXISTS (SELECT 1 FROM company.operational_worker_observations WHERE worker_name='mission-cycle-poll' AND enabled)
 AND NOT EXISTS (SELECT 1 FROM company.agent_routines r WHERE r.mission_project_id=m.project_id
 AND r.enabled AND r.kind='coordination' AND r.agent_id=m.orchestrator_agent_id)),
 'cycle_unverified',(SELECT count(*) FROM missions WHERE state IN ('planning','active','verifying')
 AND NOT EXISTS (SELECT 1 FROM company.operational_worker_observations WHERE worker_name='mission-cycle-poll')))
"""

# Check linkage where a reference exists; historical accepted/imported tasks do
# not acquire new completion requirements retrospectively.
FACTORY_QUERY = """
WITH origins AS (SELECT t.*, i.project_id planning_project, c.project_id change_project,
 coalesce(i.project_id,c.project_id) project FROM company.project_tasks t
 LEFT JOIN company.planning_items i ON i.id=t.planning_item_id
 LEFT JOIN company.change_requests c ON c.id=t.change_request_id)
SELECT json_build_object('total',count(*), 'invalid',count(*) FILTER (WHERE
 (t.planning_item_id IS NOT NULL AND t.planning_project IS NULL) OR
 (t.change_request_id IS NOT NULL AND t.change_project IS NULL) OR
 (t.planning_project IS NOT NULL AND t.change_project IS NOT NULL AND t.planning_project<>t.change_project) OR
 (t.parent_task_id IS NOT NULL AND EXISTS (SELECT 1 FROM origins p WHERE p.id=t.parent_task_id AND p.project<>t.project)) OR
 (t.status IN ('in_progress','in_review') AND t.planning_item_id IS NULL AND t.change_request_id IS NULL)))
FROM origins t
"""

REMOTE_QUERY = """
SELECT json_build_object('enabled_machines',(SELECT count(*) FROM company.servers WHERE access_enabled),
 'unobserved',(SELECT count(*) FROM company.servers s WHERE s.access_enabled AND NOT EXISTS (
 SELECT 1 FROM company.machine_status_observations o WHERE o.server_id=s.id
 AND o.last_checked_at BETWEEN now()-interval '35 minutes' AND now())),
 'source_unavailable',(SELECT count(*) FROM company.operational_worker_observations
 WHERE worker_name='machine-status-poll' AND enabled AND last_status='error'),
 'stale_executions',(SELECT count(*) FROM company.host_executions e WHERE e.status='running'
 AND (coalesce(e.heartbeat_at,e.started_at)<now()-interval '90 seconds' OR
 EXISTS (SELECT 1 FROM company.host_execution_results r WHERE r.execution_id=e.id
 AND r.status='running' AND r.started_at+make_interval(secs=>e.timeout_seconds)+interval '5 minutes'<now()
 AND (e.retry_until IS NULL OR e.retry_until<now())))),
 'missing_task',(SELECT count(*) FROM company.host_executions e WHERE e.trigger='agent'
 AND (e.agent_id IS NULL OR NOT EXISTS (SELECT 1 FROM company.agent_demands d WHERE d.id=e.agent_demand_id AND d.origin_type='task'))))
"""

SESSION_QUERY = """
SELECT json_build_object('total',count(*),'invalid',count(*) FILTER (WHERE
 ((user_id IS NULL)=(agent_id IS NULL)) OR expires_at<=created_at OR
 last_activity_at<created_at OR last_activity_at>now()+interval '1 minute'),
 'post_expiry_activity',count(*) FILTER (WHERE last_activity_at>expires_at))
FROM company.user_sessions
"""

ROUTINE_QUERY = """
SELECT json_build_object('enabled',(SELECT count(*) FROM company.agent_routines WHERE enabled),
 'overdue',count(*) FILTER (WHERE r.enabled AND x.status IN ('scheduled','running')
 AND x.occurrence_at+make_interval(mins=>r.deadline_minutes)+interval '15 minutes'<now()),
 'missing_demand',count(*) FILTER (WHERE x.status='running' AND x.demand_id IS NULL
 AND r.mission_project_id IS NULL),
 'missing_evidence',count(*) FILTER (WHERE x.status='completed' AND r.expected_evidence IS NOT NULL
 AND btrim(r.expected_evidence)<>'' AND x.no_action IS NOT TRUE AND x.evidence_received IS NOT TRUE
 AND r.mission_project_id IS NULL))
FROM company.agent_routine_runs x JOIN company.agent_routines r ON r.id=x.routine_id
"""

CHECKS = {
 'workers': ModuleCheck(WORKER_QUERY, ('registered','disabled','unhealthy'), ('unhealthy',), 5),
 'mission': ModuleCheck(MISSION_QUERY, ('total','invalid','missing_routine','cycle_unverified'), ('invalid','missing_routine','cycle_unverified')),
 'factory': ModuleCheck(FACTORY_QUERY, ('total','invalid'), ('invalid',)),
 'remote': ModuleCheck(REMOTE_QUERY, ('enabled_machines','unobserved','source_unavailable','stale_executions','missing_task'), ('unobserved','source_unavailable','stale_executions','missing_task')),
 'sessions': ModuleCheck(SESSION_QUERY, ('total','invalid','post_expiry_activity'), ('invalid','post_expiry_activity')),
 'routines': ModuleCheck(ROUTINE_QUERY, ('enabled','overdue','missing_demand','missing_evidence'), ('overdue','missing_demand','missing_evidence')),
}
