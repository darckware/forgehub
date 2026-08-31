import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { demandKeys } from "./useDemands";
import { notificationKeys } from "./useNotifications";
import {
  activityIncidentSchema,
  agentActivitySchema,
  agentActivityKeys,
  type AgentActivity,
  useAgentActivity,
  useRequestAthosMonitoring,
} from "./useAgentActivity";
import { layoutActivityNodes, layoutActivityPackets } from "./useAgentActivityViewModel";

const IDS = {
  athos: "11111111-1111-4111-8111-111111111111",
  aramis: "22222222-2222-4222-8222-222222222222",
  project: "33333333-3333-4333-8333-333333333333",
  task: "44444444-4444-4444-8444-444444444444",
  execution: "55555555-5555-4555-8555-555555555555",
  checkpoint: "66666666-6666-4666-8666-666666666666",
  message: "77777777-7777-4777-8777-777777777777",
  incidentSource: "88888888-8888-4888-8888-888888888888",
  notification: "99999999-9999-4999-8999-999999999999",
  product: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
  request: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
  concept: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
  conceptRevision: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
};

const AT = "2026-08-29T12:00:00Z";

const RECORD_LINK = {
  source_type: "task_execution",
  source_id: IDS.execution,
  canonical_path: `/api/v1/task-executions/${IDS.execution}`,
  label: "Execution",
};

const CHECKPOINT = {
  id: IDS.checkpoint,
  execution_id: IDS.execution,
  occurred_at: AT,
  status: "blocked",
  resume_from_step_key: "verify",
  summary: "Waiting for approval",
  evidence_summary: "Deployment evidence is incomplete",
  verification_summary: "No release verification yet",
  error_code: null,
  blocker_code: "approval_pending",
  canonical_path: `/api/v1/task-executions/${IDS.execution}/checkpoints/${IDS.checkpoint}`,
};

const PROFILE_SUMMARY = {
  status: "healthy",
  checked_at: AT,
  runtime_native: true,
  canonical_path: "/api/v1/agents/athos/profile-summary",
  profile_path: "/root/.hermes/athos",
  last_heartbeat_at: AT,
  issues: [],
};

const CURRENT_WORK = {
  project_id: IDS.project,
  project_name: "ForgeHub",
  project_path: `/api/v1/projects/${IDS.project}`,
  task_id: IDS.task,
  task_title: "Read model",
  task_path: `/api/v1/tasks/${IDS.task}`,
  assignment_id: null,
  work_package_id: null,
  execution_id: IDS.execution,
  execution_path: `/api/v1/task-executions/${IDS.execution}`,
  action: "Verify contract",
  branch: "agent-activity",
  working_directory_path: "/root/project/forgehub",
  requested_by_agent_id: IDS.aramis,
  source_message_id: IDS.message,
  source_message_path: `/api/v1/demands/${IDS.message}`,
};

const AGENTS = [
  {
    id: IDS.athos,
    name: "Athos",
    avatar_data_url: "data:image/png;base64,AA==",
    profile_slug: "athos",
    runtime_type: "hermes",
    availability: "busy",
    availability_reason: "execution_running",
    last_heartbeat_at: AT,
    canonical_path: `/api/v1/agents/${IDS.athos}`,
    current_work: CURRENT_WORK,
    latest_checkpoint: CHECKPOINT,
    profile_summary: PROFILE_SUMMARY,
  },
  {
    id: IDS.aramis,
    name: "Aramis",
    avatar_data_url: null,
    profile_slug: "aramis",
    runtime_type: "codex",
    availability: "available",
    availability_reason: null,
    last_heartbeat_at: AT,
    canonical_path: `/api/v1/agents/${IDS.aramis}`,
    current_work: null,
    latest_checkpoint: null,
    profile_summary: { ...PROFILE_SUMMARY, canonical_path: "/api/v1/agents/aramis/profile-summary" },
  },
] as const;

const MESSAGE_EDGE = {
  message_id: IDS.message,
  from_agent_id: IDS.aramis,
  from_agent_name: "Aramis",
  target_agent_id: IDS.athos,
  target_agent_name: "Athos",
  reply_to_id: null,
  project_id: IDS.project,
  development_request_id: null,
  product_id: null,
  task_id: IDS.task,
  subject: "Validate the canonical activity contract",
  dispatch_status: "running",
  requires_response: true,
  response_status: "pending",
  waiting_for_response: true,
  waiting_on_agent_id: IDS.athos,
  sent_at: AT,
  updated_at: "2026-08-29T12:01:00Z",
  responded_at: null,
  canonical_path: `/api/v1/demands/${IDS.message}`,
  factory_context_path: null,
};

const PRIOR_ATTEMPT = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  execution_id: IDS.execution,
  attempt_number: 1,
  started_at: AT,
  completed_at: null,
  outcome: "failed",
  error_code: "timeout",
  summary: "First attempt timed out",
  canonical_path: `/api/v1/task-executions/${IDS.execution}/attempts/1`,
  related_records: [RECORD_LINK],
};

const INCIDENT = {
  key: "execution-failed-55555555",
  kind: "execution_failed",
  severity: "error",
  title: "Execution failed",
  occurred_at: AT,
  source_type: "task_execution",
  source_id: IDS.incidentSource,
  affected_agent_id: IDS.athos,
  project_id: IDS.project,
  task_id: IDS.task,
  execution_id: IDS.execution,
  checkpoint_id: IDS.checkpoint,
  resume_from_step_key: "verify",
  error_code: "timeout",
  blocker_code: null,
  summary: "A canonical execution failure",
  recommended_action: "request_athos_monitoring",
  prior_attempts: [PRIOR_ATTEMPT],
  last_observed_at: AT,
  impact: "Release is blocked",
  runtime_type: "hermes",
  provider: "forgerouter",
  current_owner_agent_id: IDS.athos,
  canonical_path: `/api/v1/task-executions/${IDS.execution}`,
  related_records: [RECORD_LINK],
};

const ACTIVITY = {
  contract_version: "forge-agent-activity/v1",
  generated_at: AT,
  project_id: IDS.project,
  agents: AGENTS,
  contexts: [],
  projects: [
    {
      id: IDS.project,
      name: "ForgeHub",
      status: "active",
      canonical_path: `/projects/${IDS.project}`,
    },
  ],
  resources: [
    {
      key: "database:company_postgres/company",
      kind: "database",
      label: "company_postgres",
      detail: "company",
      status: "available",
    },
  ],
  topology_relations: [
    {
      key: `current-work:${IDS.athos}:${IDS.project}`,
      kind: "current_work",
      from_type: "agent",
      from_id: IDS.athos,
      to_type: "project",
      to_id: IDS.project,
      label: "Working now",
    },
    {
      key: `persistence:${IDS.project}:database:company_postgres/company`,
      kind: "persistence",
      from_type: "project",
      from_id: IDS.project,
      to_type: "resource",
      to_id: "database:company_postgres/company",
      label: "Persists in company schema",
    },
  ],
  flow_items: [
    {
      key: `task_execution:${IDS.execution}`,
      stage: "attention",
      source_type: "task_execution",
      source_id: IDS.execution,
      source_status: "failed",
      title: "Read model",
      occurred_at: AT,
      updated_at: AT,
      canonical_path: `/tasks/${IDS.task}?execution=${IDS.execution}`,
      agent_id: IDS.athos,
      project_id: IDS.project,
      task_id: IDS.task,
      execution_id: IDS.execution,
    },
  ],
  message_edges: [MESSAGE_EDGE],
  incidents: [INCIDENT],
  timeline: [
    {
      key: "execution-failed-55555555",
      kind: "execution_failed",
      occurred_at: AT,
      source_type: "task_execution",
      source_id: IDS.incidentSource,
      source_status: "failed",
      lane: "execution",
      title: "Execution failed",
      canonical_path: `/api/v1/task-executions/${IDS.execution}`,
      summary: "A canonical execution failure",
      agent_id: IDS.athos,
      project_id: IDS.project,
      task_id: IDS.task,
      execution_id: IDS.execution,
      checkpoint_id: IDS.checkpoint,
      approval_id: null,
      notification_id: IDS.notification,
      related_records: [RECORD_LINK],
    },
  ],
  source_freshness: [
    {
      name: "demands",
      status: "fresh",
      checked_at: AT,
      observed_at: AT,
      age_seconds: 0,
      detail: null,
      error_code: null,
    },
  ],
};

const PARSED_ACTIVITY: AgentActivity = agentActivitySchema.parse(ACTIVITY);

function queryWrapper(queryClient: QueryClient) {
  return function QueryWrapper({ children }: PropsWithChildren) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe("agent activity schemas", () => {
  it("parses the complete canonical read model", () => {
    expect(PARSED_ACTIVITY).toEqual(ACTIVITY);
  });

  it("rejects an incident without a canonical source id", () => {
    expect(() => activityIncidentSchema.parse({ ...INCIDENT, source_id: null })).toThrow();
  });

  it("accepts an ISO datetime without an offset when the backend serializes a naive datetime", () => {
    expect(agentActivitySchema.parse({ ...ACTIVITY, generated_at: "2026-08-29T12:00:00" }).generated_at).toBe(
      "2026-08-29T12:00:00"
    );
  });

  it("rejects malformed topology endpoints and unsupported flow stages", () => {
    expect(() => agentActivitySchema.parse({
      ...ACTIVITY,
      topology_relations: [{ ...ACTIVITY.topology_relations[0], to_type: "agent" }],
    })).toThrow();
    expect(() => agentActivitySchema.parse({
      ...ACTIVITY,
      flow_items: [{ ...ACTIVITY.flow_items[0], stage: "mystery" }],
    })).toThrow();
  });

  it("accepts a canonical conception without a project and rejects unknown context kinds", () => {
    const context = {
      context_kind: "conception",
      context_id: IDS.concept,
      product_id: IDS.product,
      product_name: "ForgeHub",
      development_request_id: IDS.request,
      concept_id: IDS.concept,
      concept_revision_id: IDS.conceptRevision,
      project_id: null,
      project_name: null,
      working_directory_path: "/root/project/forgehub",
      title: "Agent Activity continuity",
      status: "in_review",
      canonical_path: `/conception?request=${IDS.request}`,
      created_at: AT,
      updated_at: AT,
    };

    const parsed = agentActivitySchema.parse({ ...ACTIVITY, project_id: null, contexts: [context] });
    expect(parsed.contexts[0]).toMatchObject({
      context_kind: "conception",
      concept_id: IDS.concept,
      project_id: null,
    });
    expect(() => agentActivitySchema.parse({
      ...ACTIVITY,
      contexts: [{ ...context, context_kind: "workspace" }],
    })).toThrow();
  });
});

describe("agent activity data hooks", () => {
  it("queries the canonical endpoint with filter-bearing identity and parses its response", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const response = { ...ACTIVITY, transport_only_marker: "retain-before-selection" };
    const get = vi.spyOn(apiClient, "get").mockResolvedValue(response);
    const filters = { project_id: IDS.project, window_minutes: 90 };

    const { result } = renderHook(() => useAgentActivity(filters), { wrapper: queryWrapper(queryClient) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(get).toHaveBeenCalledWith("/api/v1/agent-activity", { params: filters });
    expect(result.current.data?.contract_version).toBe("forge-agent-activity/v1");
    expect(queryClient.getQueryData(agentActivityKeys.detail(filters))).toEqual(response);
    expect(queryClient.getQueryState(agentActivityKeys.detail(filters))).toBeDefined();
  });

  it("posts the canonical monitoring command and invalidates activity, messages, and notifications", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      message_id: IDS.message,
      message_number: 42,
      notification_id: IDS.notification,
      created: true,
    });
    queryClient.setQueryData(agentActivityKeys.detail({}), ACTIVITY);
    queryClient.setQueryData(demandKeys.all, []);
    queryClient.setQueryData(notificationKeys.all, []);
    const idempotencyKey = "monitor-execution-55555555";

    const { result } = renderHook(() => useRequestAthosMonitoring(), { wrapper: queryWrapper(queryClient) });
    await result.current.mutateAsync({
      incidentKey: INCIDENT.key,
      executionId: IDS.execution,
      idempotencyKey,
    });

    expect(post).toHaveBeenCalledWith(
      `/api/v1/agent-activity/incidents/${INCIDENT.key}:request-athos-monitoring`,
      { execution_id: IDS.execution, idempotency_key: idempotencyKey }
    );
    expect(queryClient.getQueryState(agentActivityKeys.detail({}))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(demandKeys.all)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(notificationKeys.all)?.isInvalidated).toBe(true);
  });
});

describe("agent activity geometry", () => {
  it("keeps selected node geometry deterministic", () => {
    expect(layoutActivityNodes(PARSED_ACTIVITY.agents)).toEqual(layoutActivityNodes(PARSED_ACTIVITY.agents));
  });

  it("sorts stable agent ids and separates overlapping ring positions without changing availability", () => {
    expect(layoutActivityNodes(PARSED_ACTIVITY.agents)).toEqual([
      {
        id: IDS.athos,
        label: "Athos",
        availability: "busy",
        xPct: 50,
        yPct: 18.84,
      },
      {
        id: IDS.aramis,
        label: "Aramis",
        availability: "available",
        xPct: 50,
        yPct: 81.16,
      },
    ]);
  });

  it("uses message id, dispatch status, and update timestamp as the stable packet identity", () => {
    const nodes = layoutActivityNodes(PARSED_ACTIVITY.agents);
    expect(layoutActivityPackets(PARSED_ACTIVITY.message_edges, nodes)).toEqual([
      {
        key: `${IDS.message}:running:2026-08-29T12:01:00Z`,
        from: { x: 50, y: 81.16 },
        to: { x: 50, y: 18.84 },
        status: "running",
        subject: "Validate the canonical activity contract",
      },
    ]);
  });
});
