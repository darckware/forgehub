import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { ActivityFlowItem } from "@/hooks/useAgentActivity";
import { CurrentFlowBoard } from "./CurrentFlowBoard";

const item = {
  key: "task_execution:11111111-1111-4111-8111-111111111111",
  stage: "attention",
  source_type: "task_execution",
  source_id: "11111111-1111-4111-8111-111111111111",
  source_status: "failed",
  title: "Build release",
  occurred_at: "2026-08-30T12:00:00Z",
  updated_at: "2026-08-30T12:05:00Z",
  canonical_path: "/tasks/release?execution=1",
  agent_id: null,
  project_id: null,
  task_id: null,
  execution_id: null,
} satisfies ActivityFlowItem;

describe("CurrentFlowBoard", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("pt-BR");
  });

  it("uses the fixed operational order and preserves canonical status", () => {
    render(<CurrentFlowBoard items={[item]} />);

    expect(screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent)).toEqual([
      "Entrada", "Planejamento", "Fila", "Execução", "Verificação", "Concluído", "Atenção", "Arquivado",
    ]);
    const attention = screen.getByRole("group", { name: /Atenção/i });
    expect(within(attention).getByRole("link", { name: /Build release.*failed/i })).toHaveAttribute(
      "href",
      "/tasks/release?execution=1",
    );
    expect(within(attention).getByText(/task_execution · failed/i)).toBeVisible();
  });

  it("explains an empty current window", () => {
    render(<CurrentFlowBoard items={[]} />);
    expect(screen.getByText(/nenhum item operacional/i)).toBeVisible();
  });
});
