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
  it("treats a generated return as delivered mail", () => {
    expect(isIncomingItem(row({ reply_to_id: "original", dispatch_status: "completed" }), "agent-b")).toBe(true);
  });

  it("keeps original executions in their lifecycle folders", () => {
    expect(isIncomingItem(row({ dispatch_status: "running" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ dispatch_status: "completed" }), "agent-b")).toBe(false);
  });

  it("does not put self-addressed or archived mail in Incoming", () => {
    expect(isIncomingItem(row({ reply_to_id: "original", from_agent_id: "agent-b" }), "agent-b")).toBe(false);
    expect(isIncomingItem(row({ reply_to_id: "original", status: "archived" }), "agent-b")).toBe(false);
  });
});
