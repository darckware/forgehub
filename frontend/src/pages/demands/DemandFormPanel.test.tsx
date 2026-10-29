import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import "@/i18n";
import { DemandFormPanel } from "./DemandFormPanel";

const mocks = vi.hoisted(() => ({ create: vi.fn().mockResolvedValue({ id: "new" }), improve: vi.fn() }));
vi.mock("@/hooks/useAgent", () => ({
  useAgents: () => ({ data: [{ id: "a", name: "Alice" }, { id: "b", name: "Bruno" }, { id: "athos", name: "Athos", profile_slug: "athos" }] }),
  useStreamTelegramImprovePrompt: () => mocks.improve,
}));
vi.mock("@/components/chat/ImprovePromptDialog", () => ({
  ImprovePromptDialog: ({ onApply, onClose }: { onApply: (text: string) => void; onClose: () => void }) => (
    <div role="dialog">
      <button onClick={() => onApply("Instrução revisada por Athos")}>Aplicar sugestão</button>
      <button onClick={onClose}>Fechar sem aplicar</button>
    </div>
  ),
}));
vi.mock("@/hooks/useProject", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/hooks/useTask", () => ({ useTasks: () => ({ data: [] }) }));
vi.mock("@/hooks/useSystemScope", () => ({ useDevelopmentRequests: () => ({ data: [] }) }));
vi.mock("@/hooks/useDemands", () => ({
  useCreateDemand: () => ({ mutateAsync: mocks.create }),
  useUpdateDemand: () => ({}),
  useUploadDemandAttachment: () => ({}),
}));

it("lists every agent as executor and keeps an explicit selection of the sender", async () => {
  render(<DemandFormPanel subject="Assunto" body="Conteúdo" onSubjectChange={vi.fn()} onBodyChange={vi.fn()} onClose={vi.fn()} />);
  const [from, to] = screen.getAllByRole("combobox");
  fireEvent.change(from, { target: { value: "a" } });
  expect(within(to).getByRole("option", { name: "Alice" })).toBeInTheDocument();
  expect(within(to).getByRole("option", { name: "Bruno" })).toBeInTheDocument();
  expect(within(to).getAllByRole("option")).toHaveLength(4);
  fireEvent.change(to, { target: { value: "a" } });
  expect(to).toHaveValue("a");
  fireEvent.click(screen.getByRole("button", { name: /Enviar/i }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ fromAgentId: "a", targetAgentId: "a" })));
});

it("preserves the demand prompt until the Athos suggestion is explicitly applied", () => {
  const onBodyChange = vi.fn();
  render(<DemandFormPanel subject="Assunto" body="Prompt original" onSubjectChange={vi.fn()} onBodyChange={onBodyChange} onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Melhorar prompt/i }));
  fireEvent.click(screen.getByRole("button", { name: "Fechar sem aplicar" }));
  expect(onBodyChange).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: /Melhorar prompt/i }));
  fireEvent.click(screen.getByRole("button", { name: "Aplicar sugestão" }));
  expect(onBodyChange).toHaveBeenCalledWith("Instrução revisada por Athos");
});
