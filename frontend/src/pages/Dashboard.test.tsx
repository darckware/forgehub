import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@/components/ToolVersionsCard", () => ({
  ToolVersionsCard: () => <div>Tool Versions</div>,
}));

vi.mock("@/components/SystemStatsCard", () => ({
  SystemStatsCard: () => <div>System Resources</div>,
}));

vi.mock("@/components/CronsCard", () => ({
  CronsCard: () => <div>Crons</div>,
}));

vi.mock("@/components/CliForgeRouterCard", () => ({
  CliForgeRouterCard: () => <div>CLI ForgeRouter</div>,
}));

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("removes the discontinued Remote Access tab", () => {
    render(<Dashboard />);

    expect(screen.getByText("System Resources")).toBeInTheDocument();
    expect(screen.queryByText("tabs.remote")).not.toBeInTheDocument();
  });
});
