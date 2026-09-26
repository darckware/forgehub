import { describe, expect, it } from "vitest";
import { parseChatStreamLine } from "./useChat";

// Lines in the shape host-bridge's _claude_events emits for a subagent run
// (see host-bridge/tests/test_claude_subagent_events.py for the real capture).
describe("parseChatStreamLine -- subagents", () => {
  it("reads a subagent launch", () => {
    const event = parseChatStreamLine(JSON.stringify({
      tool_start: { tool_id: "t1", name: "Agent", context: "soma", subagent: { description: "soma", subagent_type: "general-purpose" } },
    }));
    expect(event).toMatchObject({ type: "tool_start", toolId: "t1", subagent: { description: "soma", subagentType: "general-purpose" } });
  });

  it("reads a step a subagent ran", () => {
    const event = parseChatStreamLine(JSON.stringify({ tool_start: { tool_id: "s1", name: "Bash", context: "echo 4", parent_id: "t1" } }));
    expect(event).toMatchObject({ type: "tool_start", toolId: "s1", parentId: "t1" });
  });

  it("reads subagent text as its own event, never as a reply delta", () => {
    expect(parseChatStreamLine(JSON.stringify({ subagent_delta: { parent_id: "t1", text: "4" } }))).toEqual({
      type: "subagent_delta",
      parentId: "t1",
      text: "4",
    });
  });

  it("reads subagent status", () => {
    const event = parseChatStreamLine(JSON.stringify({
      subagent_status: { tool_id: "t1", status: "running", description: "soma", subagent_type: "general-purpose", backgrounded: true },
    }));
    expect(event).toMatchObject({ type: "subagent_status", toolId: "t1", status: "running", backgrounded: true });
  });

  it("reads a completion with its parent and error flag", () => {
    const event = parseChatStreamLine(JSON.stringify({ tool_complete: { tool_id: "s1", parent_id: "t1", is_error: true } }));
    expect(event).toMatchObject({ type: "tool_complete", toolId: "s1", parentId: "t1", isError: true });
  });

  it("still reads a plain reply delta", () => {
    expect(parseChatStreamLine(JSON.stringify({ delta: "oi" }))).toEqual({ type: "delta", text: "oi" });
  });
});
