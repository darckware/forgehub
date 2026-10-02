import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { HindsightStatus } from "@/hooks/useHindsight";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) => vars ? `${key} ${JSON.stringify(vars)}` : key,
    i18n: { language: "pt-BR" },
  }),
}));

import { HindsightRetentionCard } from "./HindsightRetentionCard";

it("shows the active policy, candidate counts, and Knowledge Base destination", () => {
  const retention: NonNullable<HindsightStatus["retention"]> = {
    checked_at: "2026-10-02T10:00:00Z", review_days: 90, compact_days: 180,
    recovery_days: 60, mode: "preview", total_documents: 2206,
    review_count: 104, eligible_count: 0, protected_count: 2,
    compacted_count: 0, purged_count: 0, error_count: 0,
    discontinued_topics_count: 1, discarded_topics_count: 0,
  };
  render(<MemoryRouter><HindsightRetentionCard retention={retention} /></MemoryRouter>);
  expect(screen.getByText(/retention\.reviewCount/)).toHaveTextContent("104");
  expect(screen.getByText(/retention\.eligibleCount/)).toHaveTextContent("0");
  expect(screen.getByText(/retention\.discontinuedCount/)).toHaveTextContent("1");
  expect(screen.getByRole("link", { name: /retention\.openKnowledgeBase/ })).toHaveAttribute("href", "/obsidian");
});

it("does not imply the policy ran before the first report exists", () => {
  render(<MemoryRouter><HindsightRetentionCard retention={null} /></MemoryRouter>);
  expect(screen.getByText("retention.awaitingReport")).toBeInTheDocument();
});
