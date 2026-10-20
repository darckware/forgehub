import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { ActivityTimelineEvent } from "@/hooks/useAgentActivity";
import { ContinuityTimeline } from "./ContinuityTimeline";

const baseEvent: Omit<ActivityTimelineEvent, "key" | "title" | "lane" | "occurred_at"> = {
  kind: "message_sent",
  source_type: "agent_demand",
  source_status: "dispatched",
  source_id: "11111111-1111-4111-8111-111111111111",
  canonical_path: "/demands?message=1",
  summary: null,
  agent_id: null,
  project_id: null,
  task_id: null,
  execution_id: null,
  checkpoint_id: null,
  approval_id: null,
  notification_id: null,
  related_records: [],
};

const events: ActivityTimelineEvent[] = [
  { ...baseEvent, key: "later", title: "Later message", lane: "communication", occurred_at: "2026-08-30T13:00:00-03:00" },
  { ...baseEvent, key: "earlier", title: "Earlier message", lane: "communication", occurred_at: "2026-08-30T15:00:00Z" },
  { ...baseEvent, key: "execution", title: "Execution running", lane: "execution", source_type: "task_execution", source_status: "running", occurred_at: "2026-08-30T15:30:00Z" },
];

describe("ContinuityTimeline", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("groups events into ordered semantic lanes and sorts real instants", () => {
    render(<ContinuityTimeline events={events} selectedAgentId={null} />);

    expect(screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent)).toEqual([
      "Communication", "Planning", "Execution", "Checkpoints", "Governance",
    ]);
    const communication = screen.getByRole("group", { name: "Communication" });
    expect(within(communication).getAllByRole("link").map((node) => node.textContent)).toEqual([
      expect.stringContaining("Earlier message"),
      expect.stringContaining("Later message"),
    ]);
    expect(within(communication).getAllByText(/agent_demand · dispatched/i)).toHaveLength(2);
  });

  it("retains the explicit empty history state", () => {
    render(<ContinuityTimeline events={[]} selectedAgentId={null} />);
    expect(screen.getByText(/no continuity events/i)).toBeVisible();
  });
});
