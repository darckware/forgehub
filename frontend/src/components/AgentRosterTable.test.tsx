import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { agentSchema, type Agent } from "@/hooks/useAgent";
import { AgentRosterTable, sortAgents } from "./AgentRosterTable";


function agent(id: string, name: string, overrides: Partial<Agent> = {}): Agent {
  return agentSchema.parse({
    id,
    name,
    mission: `${name} mission`,
    runtime_type: "hermes",
    runtime_tier: "A",
    department: "Governance",
    status: "active",
    ...overrides,
  });
}

const AGENTS = [agent("2", "Athos"), agent("1", "Aegis")];


describe("sortAgents", () => {
  it("sorts by the requested column without mutating the API result", () => {
    const original = [...AGENTS];

    expect(sortAgents(AGENTS, "name", "asc").map((item) => item.name)).toEqual([
      "Aegis",
      "Athos",
    ]);
    expect(sortAgents(AGENTS, "name", "desc").map((item) => item.name)).toEqual([
      "Athos",
      "Aegis",
    ]);
    expect(AGENTS).toEqual(original);
  });
});


describe("AgentRosterTable", () => {
  it("exposes the active sort direction and requests the opposite direction", () => {
    const onSort = vi.fn();
    render(
      <AgentRosterTable
        agents={AGENTS}
        sortKey="name"
        sortDirection="asc"
        expandedAgentId={null}
        onSort={onSort}
        onToggle={() => undefined}
        renderDetails={() => null}
      />,
    );

    const nameHeader = screen.getByRole("columnheader", { name: /agente/i });
    expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(within(nameHeader).getByRole("button"));
    expect(onSort).toHaveBeenCalledWith("name");
  });

  it("opens only the selected detail row and supports keyboard activation", () => {
    function Harness() {
      const [expanded, setExpanded] = useState<string | null>(null);
      return (
        <AgentRosterTable
          agents={AGENTS}
          sortKey="name"
          sortDirection="asc"
          expandedAgentId={expanded}
          onSort={() => undefined}
          onToggle={(id) => setExpanded((current) => current === id ? null : id)}
          renderDetails={(item) => <p>Detalhes de {item.name}</p>}
        />
      );
    }
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /Athos/ }));
    expect(screen.getByText("Detalhes de Athos")).toBeInTheDocument();

    const aegisToggle = screen.getByRole("button", { name: /Aegis/ });
    aegisToggle.focus();
    expect(aegisToggle).toHaveFocus();
    fireEvent.click(aegisToggle);
    expect(screen.getByText("Detalhes de Aegis")).toBeInTheDocument();
    expect(screen.queryByText("Detalhes de Athos")).not.toBeInTheDocument();
  });
});
