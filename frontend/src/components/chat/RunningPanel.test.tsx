import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChatSubagent } from "@/lib/chatSubagents";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));
vi.mock("@/hooks/useDemands", () => ({
  useDemands: () => ({
    data: [
      { number: 7, subject: "Revisar deploy", dispatch_status: "dispatched", target_agent_id: "a1" },
      { number: 8, subject: "Já feito", dispatch_status: "completed", target_agent_id: "a1", dispatch_result: "pronto" },
    ],
  }),
}));
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [{ id: "a1", name: "Athos" }] }) }));
vi.mock("@/components/Markdown", () => ({ Markdown: ({ content }: { content: string }) => <div>{content}</div> }));

import { RunningPanel } from "./RunningPanel";

const sub = (patch: Partial<ChatSubagent>): ChatSubagent => ({
  id: "toolu_1",
  description: "Explorar o repo",
  subagentType: "Explore",
  status: "running",
  text: "",
  steps: [],
  ...patch,
});

function renderPanel(subagents: ChatSubagent[], delegationNumbers: number[] = []) {
  return render(
    <RunningPanel
      subagents={subagents}
      delegationNumbers={delegationNumbers}
      renderSteps={(steps) => <ul data-testid="steps">{steps.map((s) => <li key={s.id}>{s.label}</li>)}</ul>}
      renderDelegation={(n) => <div data-testid="delegation-card">card {n}</div>}
    />
  );
}

describe("RunningPanel", () => {
  it("renders nothing when there is nothing to list", () => {
    const { container } = renderPanel([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists running subagents and delegations, and hides finished ones until expanded", () => {
    renderPanel([sub({}), sub({ id: "toolu_2", description: "Antigo", status: "completed" })], [7, 8]);
    expect(screen.getByText("Explorar o repo")).toBeInTheDocument();
    expect(screen.getByText("Revisar deploy")).toBeInTheDocument();
    expect(screen.queryByText("Antigo")).not.toBeInTheDocument();
    expect(screen.queryByText("Já feito")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/running\.finished/));
    expect(screen.getByText("Antigo")).toBeInTheDocument();
    expect(screen.getByText("Já feito")).toBeInTheDocument();
  });

  it("swaps to a subagent's own steps and output, and back to the list", () => {
    renderPanel([
      sub({ text: "achei 3 arquivos", steps: [{ id: "s1", name: "Grep", label: "grep foo", done: true }] }),
    ]);
    fireEvent.click(screen.getByText("Explorar o repo"));
    expect(screen.getByTestId("steps")).toHaveTextContent("grep foo");
    expect(screen.getByText("achei 3 arquivos")).toBeInTheDocument();

    fireEvent.click(screen.getByText("running.main"));
    expect(screen.queryByTestId("steps")).not.toBeInTheDocument();
    expect(screen.getByText("Explorar o repo")).toBeInTheDocument();
  });

  it("opens a delegation with its status card and result", () => {
    renderPanel([], [8]);
    fireEvent.click(screen.getByText(/running\.finished/));
    fireEvent.click(screen.getByText("Já feito"));
    expect(screen.getByTestId("delegation-card")).toHaveTextContent("card 8");
    expect(screen.getByText("pronto")).toBeInTheDocument();
  });
});
