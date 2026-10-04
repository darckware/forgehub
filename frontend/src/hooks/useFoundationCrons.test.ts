import { describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { cronJobSchema } from "./useFoundationCrons";
import { fetchScriptContent } from "./useFoundationScripts";

const oldJob = {
  profile: "athos",
  id: "job-1",
  name: "ecosystem-weekly-audit",
  description: null,
  script: "ecosystem_weekly_audit.sh",
  schedule_display: "0 19 * * 0",
  enabled: true,
  state: "scheduled",
  status: "active",
  health: "ok",
  next_run_at: null,
  last_run_at: null,
  last_status: null,
  last_error: null,
  last_log_at: null,
  deliver: null,
};

describe("Foundation cron contracts", () => {
  it("defaults new fields when parsing an older API response", () => {
    const job = cronJobSchema.parse(oldJob);
    expect(job.script_state).toBe("none");
    expect(job.is_audit_job).toBe(false);
  });

  it("keeps operational fields from a current API response", () => {
    const job = cronJobSchema.parse({ ...oldJob, script_state: "broken", is_audit_job: true });
    expect(job.script_state).toBe("broken");
    expect(job.is_audit_job).toBe(true);
  });

  it("reads content from the owning profile", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ content: "echo ready", path: "/profiles/athos/scripts/job.sh" });
    try {
      const content = await fetchScriptContent({ location: "athos", name: "job.sh" });
      expect(content.content).toBe("echo ready");
      expect(get).toHaveBeenCalledWith("/api/v1/foundation/scripts/athos/job.sh/content");
    } finally {
      get.mockRestore();
    }
  });
});
