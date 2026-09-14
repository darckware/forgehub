import { describe, expect, it } from "vitest";
import { computeInboxTotalCount, isIncomingItem, type Demand } from "./useDemands";

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
