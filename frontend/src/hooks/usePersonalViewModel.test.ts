import { describe, expect, it } from "vitest";
import { groupAgendaByDay, groupTasks } from "./usePersonalViewModel";
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
