import { describe, expect, it } from "vitest";
import { computeInboxTotalCount, isIncomingItem, isExecutionOpen, executionStage, isRetentionEligible, type Demand } from "./useDemands";

function row(overrides: Partial<Demand>): Demand {
  return {
    status: "new",
    target_agent_id: "agent-b",
    from_agent_id: "agent-a",
    reply_to_id: null,
    dispatch_status: null,
    ...overrides,
  } as Demand;
}

describe("execution tracking", () => {
  it.each(["dispatched", "running", "failed"] as const)("keeps %s attempts in execution until completion is accepted", dispatch_status => {
    expect(isExecutionOpen(row({ dispatch_status }))).toBe(true);
    expect(isExecutionOpen(row({ dispatch_status, status: "archived" }))).toBe(false);
  });
  it("excludes accepted completions and work not yet dispatched", () => {
    expect(isExecutionOpen(row({ dispatch_status: "completed" }))).toBe(false);
    expect(isExecutionOpen(row({ dispatch_status: null }))).toBe(false);
  });
  it("distinguishes an ended attempt from a running process", () => {
    expect(executionStage(row({ dispatch_status: "running" }))).toBe("running");
    expect(executionStage(row({ dispatch_status: "failed", dispatch_error: "The agent reported STATUS: BLOCKED; the work is not finished." }))).toBe("blocked");
    expect(executionStage(row({ dispatch_status: "failed", dispatch_error: "The agent run ended without the completion report (STATUS: DONE | PARTIAL | BLOCKED); the work may be unfinished." }))).toBe("awaitingVerification");
    expect(executionStage(row({ dispatch_status: "failed", dispatch_error: "The agent reported STATUS: PARTIAL; the work is not finished." }))).toBe("needsCorrection");
  });
  it("keeps a reprocessed attempt in execution while waiting in the queue", () => {
    const queued = row({ target_agent_id: "agent-b", from_agent_id: "agent-b", dispatch_status: null, dispatch_attempts: 1, scheduled_at: "2026-10-29T10:00:00Z" });
    expect(isExecutionOpen(queued)).toBe(true);
    expect(isIncomingItem(queued, "agent-b")).toBe(false);
    expect(executionStage(queued)).toBe("queuedRetry");
  });
  it("protects unresolved attempts from retention cleanup", () => {
    expect(isRetentionEligible(row({ dispatch_status: "failed" }))).toBe(false);
    expect(isRetentionEligible(row({ dispatch_status: "running" }))).toBe(false);
    expect(isRetentionEligible(row({ dispatch_status: "completed" }))).toBe(true);
    expect(isRetentionEligible(row({ dispatch_status: "failed", status: "archived" }))).toBe(true);
  });
  it("keeps a diagnostic failure blocked and protects its evidence", () => {
    const check = row({ failure_check_source_id: "original", dispatch_status: "failed", dispatch_error: "CLI error" });
    expect(isExecutionOpen(check)).toBe(true);
    expect(executionStage(check)).toBe("blocked");
    expect(isRetentionEligible({ ...check, status: "archived" })).toBe(false);
  });
});

describe("isIncomingItem", () => {
  it("keeps self-addressed incubation out of Incoming and its badge", () => {
    const item = row({ origin_type: "incubation", from_agent_id: "agent-b", target_agent_id: "agent-b" });
    expect(isIncomingItem(item, "agent-b")).toBe(false);
    expect(computeInboxTotalCount([item])).toBe(0);
  });
  it("counts self-addressed work as Incoming while it hasn't started (2026-08-15)", () => {
    expect(
      isIncomingItem(row({ target_agent_id: "agent-b", from_agent_id: "agent-b", dispatch_status: null }), "agent-b")
    ).toBe(true);
  });

  it("never counts a cross-agent message as Incoming -- pending is retired, nothing ever writes it", () => {
    expect(isIncomingItem(row({ dispatch_status: null }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "pending" as Demand["dispatch_status"] }), "agent-b")).toBe(false);
  });

  it("keeps every dispatch lifecycle stage out of Incoming, generated returns included", () => {
    const self = { target_agent_id: "agent-b", from_agent_id: "agent-b" };
    expect(isIncomingItem(row({ ...self, dispatch_status: "dispatched" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ ...self, dispatch_status: "running" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ ...self, dispatch_status: "failed" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ ...self, dispatch_status: "completed" }), "agent-b")).toBe(false);
    // A generated return is created already-terminal (dispatch_status="completed")
    // and belongs in Completed like any other terminal row, not Incoming.
    expect(isIncomingItem(row({ reply_to_id: "original", dispatch_status: "completed" }), "agent-b")).toBe(false);
  });

  it("does not put archived mail in Incoming", () => {
    expect(
      isIncomingItem(row({ target_agent_id: "agent-b", from_agent_id: "agent-b", status: "archived" }), "agent-b")
    ).toBe(false);
  });
});

describe("computeInboxTotalCount", () => {
  it("counts a no-target, no-sender row as System", () => {
    expect(computeInboxTotalCount([row({ target_agent_id: null, from_agent_id: null })])).toBe(1);
  });

  it("does not double-count a no-target Incubation row that already has an owner (não existe anônima)", () => {
    expect(computeInboxTotalCount([row({ target_agent_id: null, from_agent_id: "agent-a" })])).toBe(0);
  });

  it("counts self-addressed not-yet-started work", () => {
    expect(
      computeInboxTotalCount([row({ target_agent_id: "agent-b", from_agent_id: "agent-b", dispatch_status: null })])
    ).toBe(1);
  });
});
