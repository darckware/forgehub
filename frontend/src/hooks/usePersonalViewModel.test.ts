import { describe, expect, it } from "vitest";
import { NO_TYPE, groupAgendaByDay, groupDemands, groupTasks } from "./usePersonalViewModel";
import { addDays, joinLocal, splitLocal } from "./usePersonal";
import type { AgendaItem, PersonalTask } from "./usePersonal";

const task = (id: string, due_at: string | null) => ({ id, title: id, due_at } as PersonalTask);
const item = (id: string, starts_at: string, overdue = false) => ({ id, kind: "task", starts_at, overdue } as AgendaItem);

describe("personal view model helpers", () => {
  it("groups tasks into overdue, today, upcoming and no date", () => {
    const g = groupTasks(
      [task("a", "2026-10-07T00:00:00"), task("b", "2026-10-08T10:00:00"), task("c", "2026-10-09T00:00:00"), task("d", null)],
      "2026-10-08",
    );
    expect([g.overdue, g.today, g.upcoming, g.noDate].map((x) => x.map((t) => t.id))).toEqual([["a"], ["b"], ["c"], ["d"]]);
  });

  it("puts overdue first and sorts days", () => {
    const days = groupAgendaByDay([item("x", "2026-10-10T09:00:00"), item("y", "2026-10-01T08:00:00", true), item("z", "2026-10-09T08:00:00")]);
    expect(days.map(([d]) => d)).toEqual(["overdue", "2026-10-09", "2026-10-10"]);
  });

  it("builds and splits local datetimes without timezone shifts", () => {
    expect(joinLocal("2026-10-08", "15:30")).toBe("2026-10-08T15:30:00");
    expect(joinLocal("2026-10-08")).toBe("2026-10-08T00:00:00");
    expect(splitLocal("2026-10-08T15:30:00")).toEqual({ date: "2026-10-08", time: "15:30" });
    expect(addDays("2026-12-25", 14)).toBe("2027-01-08");
  });
});

describe("groupDemands", () => {
  const type = (id: string, name: string) => ({ id, name, created_by: "marcelo", created_at: "" });
  const demand = (id: string, type_id: string | null) => ({
    id, title: id, notes: null, type_id, status: "open" as const, completed_at: null,
    created_by: "marcelo", created_at: "", updated_at: "",
  });

  it("groups in the types' order, then demands with no (or a removed) type, skipping empty groups", () => {
    const groups = groupDemands(
      [demand("a", "t2"), demand("b", null), demand("c", "t1"), demand("d", "gone")],
      [type("t1", "Casa"), type("t2", "SEMED"), type("t3", "Vazio")],
    );
    expect(groups.map((g) => [g.typeId, g.demands.map((d) => d.id)])).toEqual([
      ["t1", ["c"]],
      ["t2", ["a"]],
      [NO_TYPE, ["b", "d"]],
    ]);
  });
});
