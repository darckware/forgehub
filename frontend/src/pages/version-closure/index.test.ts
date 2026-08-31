import { describe, expect, it } from "vitest";
import type { Project } from "@/hooks/useProject";
import type { ProjectTask } from "@/hooks/useTask";
import { deriveVersionReadiness } from "./index";

describe("deriveVersionReadiness", () => {
  it("keeps publication blocked by a pending task in a sibling project", () => {
    const projects = [
      { id: "project-a", name: "API", product_version_id: "version-1" },
      { id: "project-b", name: "Web", product_version_id: "version-1" },
      { id: "project-c", name: "Other version", product_version_id: "version-2" },
    ] as Project[];
    const tasks = [
      { id: "task-a", project_id: "project-a", status: "done" },
      { id: "task-b", project_id: "project-b", status: "planned" },
      { id: "task-c", project_id: "project-c", status: "planned" },
    ] as ProjectTask[];

    const result = deriveVersionReadiness(projects, tasks, "version-1");

    expect(result.projects.map((project) => project.id)).toEqual(["project-a", "project-b"]);
    expect(result.tasks.map((task) => task.id)).toEqual(["task-a", "task-b"]);
    expect(result.pending.map((task) => task.id)).toEqual(["task-b"]);
    expect(result.eligible).toBe(false);
  });

  it("requires at least one task even when no task is pending", () => {
    const result = deriveVersionReadiness(
      [{ id: "project-a", name: "API", product_version_id: "version-1" }] as Project[],
      [],
      "version-1",
    );
    expect(result.eligible).toBe(false);
  });
});
