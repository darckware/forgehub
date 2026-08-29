import { describe, expect, it } from "vitest";
import { agentSchema, isExternalRuntime, profileFileNamesFor, subAgentsFileName } from "./useAgent";

/**
 * `profileFileNamesFor` mirrors `allowed_filenames` in
 * backend/app/core/agent_profile_files.py -- the org chart renders one chip
 * per file without asking the server, so a drift between the two shows up as
 * a chip that 404s on click. These tests pin the mirror.
 */
describe("profileFileNamesFor", () => {
  it("lists the nine canonical files for a Hermes profile, plus its SUBAGENTS file", () => {
    expect(profileFileNamesFor({ runtime_type: "hermes", profile_slug: "athos" })).toEqual([
      "SOUL.md",
      "IDENTITY.md",
      "USER.md",
      "TOOLS.md",
      "AGENTS.md",
      "FOUNDATION_LINK.md",
      "HEARTBEAT.md",
      "MEMORY.md",
      "CONTINUITY.md",
      "ATHOS_SUBAGENTS.md",
    ]);
  });

  it("adds CLAUDE.md for the claude runtime -- its native always-loaded entrypoint", () => {
    const files = profileFileNamesFor({ runtime_type: "claude", profile_slug: "porthus" });
    expect(files).toContain("CLAUDE.md");
    expect(files).toContain("AGENTS.md");
    // The runtime extra comes after the canonical set, before SUBAGENTS.
    expect(files.indexOf("CLAUDE.md")).toBeGreaterThan(files.indexOf("CONTINUITY.md"));
    expect(files.at(-1)).toBe("PORTHUS_SUBAGENTS.md");
  });

  it("omits the SUBAGENTS file when the agent has no profile slug", () => {
    const files = profileFileNamesFor({ runtime_type: null, profile_slug: null });
    expect(files.some((name) => name.endsWith("_SUBAGENTS.md"))).toBe(false);
    expect(files).toHaveLength(9);
  });

  it("upper-cases the slug and converts hyphens, like the backend contract naming", () => {
    expect(subAgentsFileName("my-agent")).toBe("MY_AGENT_SUBAGENTS.md");
    expect(subAgentsFileName(null)).toBeNull();
  });
});

describe("isExternalRuntime", () => {
  it("treats every runtime except hermes as external", () => {
    expect(isExternalRuntime("hermes")).toBe(false);
    expect(isExternalRuntime("claude")).toBe(true);
    expect(isExternalRuntime("codex")).toBe(true);
    expect(isExternalRuntime("agy")).toBe(true);
    expect(isExternalRuntime("openclaw")).toBe(true);
  });

  it("is not external when there is no runtime at all", () => {
    // A hand-registered agent with no dispatchable runtime must not be filed
    // under "external CLI runtimes" in the org chart.
    expect(isExternalRuntime(null)).toBe(false);
    expect(isExternalRuntime(undefined)).toBe(false);
  });
});

describe("agentSchema avatar", () => {
  it("keeps the optional avatar data URL returned by the API", () => {
    const parsed = agentSchema.parse({
      id: "agent-1",
      name: "Athos",
      avatar_data_url: "data:image/png;base64,iVBORw0KGgo=",
    });

    expect(parsed.avatar_data_url).toBe("data:image/png;base64,iVBORw0KGgo=");
  });
});
