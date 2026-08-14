import { describe, expect, it } from "vitest";
import { isIncomingItem, type Demand } from "./useDemands";

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
  it("counts a pending addressed message as Incoming", () => {
    expect(isIncomingItem(row({ dispatch_status: "pending" }), "agent-b")).toBe(true);
  });

  it("keeps every dispatch lifecycle stage out of Incoming, generated returns included", () => {
    expect(isIncomingItem(row({ dispatch_status: "dispatched" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "running" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "failed" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "completed" }), "agent-b")).toBe(false);
    // A generated return is created already-terminal (dispatch_status="completed")
    // and belongs in Completed like any other terminal row, not Incoming.
    expect(isIncomingItem(row({ reply_to_id: "original", dispatch_status: "completed" }), "agent-b")).toBe(false);
  });

  it("does not put self-addressed or archived mail in Incoming", () => {
    expect(isIncomingItem(row({ dispatch_status: "pending", from_agent_id: "agent-b" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "pending", status: "archived" }), "agent-b")).toBe(false);
  });
});
