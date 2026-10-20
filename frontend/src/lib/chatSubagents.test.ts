import { describe, expect, it } from "vitest";
import { onSubagentLaunched, onSubagentStatus, onSubagentStep, onSubagentStepDone, onSubagentText, onToolCompleted, settleSubagents } from "./chatSubagents";

describe("chat subagents", () => {
  it("tracks a launched subagent until its launch returns", () => {
    let map = onSubagentLaunched(undefined, "t1", { description: "soma", subagentType: "general-purpose" });
    expect(map.t1).toMatchObject({ description: "soma", status: "running", text: "" });
    map = onToolCompleted(map, "t1");
    expect(map.t1.status).toBe("completed");
  });

  it("does not finish a backgrounded subagent when its launch returns", () => {
    let map = onSubagentLaunched(undefined, "t1", { description: "soma" });
    map = onSubagentStatus(map, { toolId: "t1", status: "running", backgrounded: true });
    map = onToolCompleted(map, "t1");
    expect(map.t1.status).toBe("running");
    map = onSubagentStatus(map, { toolId: "t1", status: "completed", summary: "feito" });
    expect(map.t1).toMatchObject({ status: "completed", summary: "feito" });
  });

  it("keeps the subagent's text apart and accumulates it", () => {
    let map = onSubagentText(undefined, "t1", "4");
    map = onSubagentText(map, "t1", "2");
    expect(map.t1.text).toBe("42");
  });

  it("keeps the subagent's own steps and completes them", () => {
    let map = onSubagentLaunched(undefined, "t1", {});
    map = onSubagentStep(map, "t1", { id: "s1", name: "Bash", label: "echo 4", done: false });
    map = onSubagentStepDone(map, "t1", "s1");
    expect(map.t1.steps).toEqual([{ id: "s1", name: "Bash", label: "echo 4", done: true }]);
  });

  it("marks a failed launch as failed", () => {
    const map = onToolCompleted(onSubagentLaunched(undefined, "t1", {}), "t1", true);
    expect(map.t1.status).toBe("failed");
  });

  it("ignores completions of ordinary tools", () => {
    const map = onSubagentLaunched(undefined, "t1", {});
    expect(onToolCompleted(map, "other")).toBe(map);
  });

  it("settles anything still running when the turn ends", () => {
    let map = onSubagentLaunched(undefined, "a", {});
    map = onSubagentLaunched(map, "b", {});
    map = onToolCompleted(map, "b");
    const settled = settleSubagents(map, "stopped");
    expect(settled.a.status).toBe("stopped");
    expect(settled.b.status).toBe("completed");
  });
});
