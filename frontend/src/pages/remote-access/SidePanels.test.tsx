/** Every Remote Access form opens as a right-hand panel (2026-11-11, Marcelo:
 * "não quero essa tela modal. O formulário precisa abrir a direita"): a
 * labelled dialog sliding in from the right that Escape closes -- except
 * while a request is in flight -- taking focus in and giving it back to the
 * button that opened it. */
import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";
import { ImportCsvModal, InstallKeyModal } from "@/pages/servers/ServerDialogs";
import { AgentRequestDialog } from "./AgentRequestDialog";
import { MaintenanceDialog } from "./MaintenanceDialog";
import { PrepareDialog } from "./PrepareDialog";
import { RevealPasswordDialog } from "./RevealPasswordDialog";
import { RotationDialog } from "./RotationDialog";
import { ScriptCategoriesDialog } from "./ScriptCategoriesDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const machine = { id: "m1", name: "PC-01", ip_address: "100.64.0.1", remote_user: "darckware", ssh_port: 22, os_family: "windows" } as unknown as Server;

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

const cases: [string, string | RegExp, (onClose: () => void) => ReactNode][] = [
  ["AgentRequestDialog", "Pedir ao agente", (onClose) => <AgentRequestDialog machines={[machine]} onClose={onClose} />],
  ["PrepareDialog", /./, (onClose) => <PrepareDialog onClose={onClose} onExecution={vi.fn()} />],
  ["RotationDialog", /./, (onClose) => <RotationDialog kind="ssh_key" onClose={onClose} onExecution={vi.fn()} />],
  ["MaintenanceDialog", /PC-01/, (onClose) => <MaintenanceDialog machine={machine} onClose={onClose} />],
  ["ScriptCategoriesDialog", /./, (onClose) => <ScriptCategoriesDialog onClose={onClose} />],
  ["RevealPasswordDialog", /PC-01/, (onClose) => <RevealPasswordDialog machine={machine} onClose={onClose} />],
  ["InstallKeyModal", /srv|PC-01/, (onClose) => <InstallKeyModal server={machine} onClose={onClose} onInstalled={vi.fn()} />],
  ["ImportCsvModal", /./, (onClose) => <ImportCsvModal onClose={onClose} />],
];

const never = () => new Promise(() => undefined) as never;
const agentRow = (id: string, name: string) => ({ id, name, is_active: true, status: "active", agent_type: "executor" });

/** The data each panel needs to reach its submit button. */
function mockApi() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return [{ ...machine, ssh_key_path: "/k", kind: "workstation" }] as never;
    if (url === "/api/v1/servers/readiness") return { entries: [{ server_id: "m1", readiness: "not_prepared" }] } as never;
    if (url.startsWith("/api/v1/agents")) return [agentRow("a1", "Aegis")] as never;
    if (url.startsWith("/api/v1/governed/authority-delegations")) {
      return [{ id: "d1", grantee_id: "a1", servers: ["m1"], host_groups: [], scope_type: "organization",
        allowed_actions: ["remote_access.execute"], status: "active", max_risk: "high",
        expires_at: new Date(Date.now() + 86_400_000).toISOString() }] as never;
    }
    return [] as never;
  });
}

/** Opens the panel from a real button, like the screen does. */
function Opener({ panel }: { panel: (onClose: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Abrir painel</button>
      {open && panel(() => setOpen(false))}
    </>
  );
}

describe("Remote Access side panels", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockApi();
    await i18n.changeLanguage("pt-BR");
  });

  it.each(cases)("%s opens on the right and closes on Escape", (_name, title, node) => {
    const onClose = vi.fn();
    wrap(node(onClose));
    const panel = screen.getByRole("dialog", { name: title });
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(panel.className).toContain("slide-in-from-right");
    expect(panel.parentElement?.className).toContain("justify-end");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it.each(cases)("%s takes focus on open and gives it back to the opener on close", (_name, _title, node) => {
    wrap(<Opener panel={node} />);
    const opener = screen.getByRole("button", { name: "Abrir painel" });
    opener.focus();
    fireEvent.click(opener);
    const panel = screen.getByRole("dialog");
    expect(panel.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  /** Each form, with its request left hanging: Escape and the overlay must not close it. */
  const busyCases: [string, (onClose: () => void) => ReactNode, () => Promise<void> | void, (() => void)?][] = [
    ["RevealPasswordDialog", (onClose) => <RevealPasswordDialog machine={machine} onClose={onClose} />, () => {
      vi.mocked(apiClient.get).mockImplementation(never);
      fireEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    }],
    ["RotationDialog", (onClose) => <RotationDialog kind="ssh_key" onClose={onClose} onExecution={vi.fn()} />, async () => {
      vi.mocked(apiClient.post).mockImplementation(never);
      fireEvent.click(await screen.findByRole("checkbox", { name: /PC-01/ }));
      fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
      fireEvent.click(screen.getByRole("button", { name: "Rotacionar (1)" }));
    }, () => {
      // rotation only lists Ready machines
      vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
        url === "/api/v1/servers/readiness" ? { entries: [{ server_id: "m1", readiness: "ready" }] } as never
          : url === "/api/v1/servers" ? [{ ...machine, ssh_key_path: "/k" }] as never : [] as never);
    }],
    ["PrepareDialog", (onClose) => <PrepareDialog initialServerId="m1" onClose={onClose} onExecution={vi.fn()} />, async () => {
      vi.mocked(apiClient.put).mockImplementation(never);
      vi.mocked(apiClient.post).mockImplementation(never);
      await screen.findByRole("option", { name: /PC-01/ });
      fireEvent.click(screen.getByRole("radio", { name: "Outra conta" }));
      fireEvent.change(screen.getByLabelText("Login do administrador"), { target: { value: "Administrador" } });
      fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "secret" } });
      fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    }],
    ["AgentRequestDialog", (onClose) => <AgentRequestDialog machines={[machine]} onClose={onClose} />, async () => {
      vi.mocked(apiClient.post).mockImplementation(never);
      fireEvent.change(screen.getByLabelText("O que fazer"), { target: { value: "Reinicie o spooler" } });
      fireEvent.click(await screen.findByRole("checkbox", { name: /Aegis/ }));
      fireEvent.click(screen.getByRole("button", { name: "Enviar a 1 agente" }));
    }],
    ["ScriptCategoriesDialog", (onClose) => <ScriptCategoriesDialog onClose={onClose} />, () => {
      vi.mocked(apiClient.post).mockImplementation(never);
      fireEvent.change(screen.getByLabelText("Nova classificação"), { target: { value: "Impressoras" } });
      fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
    }],
    ["InstallKeyModal", (onClose) => <InstallKeyModal server={machine} onClose={onClose} onInstalled={vi.fn()} />, () => {
      vi.mocked(apiClient.put).mockImplementation(never);
      vi.mocked(apiClient.post).mockImplementation(never);
      fireEvent.change(screen.getByDisplayValue(""), { target: { value: "secret" } });
      fireEvent.click(screen.getByRole("button", { name: "Instalar chave" }));
    }],
    ["ImportCsvModal", (onClose) => <ImportCsvModal onClose={onClose} />, () => {
      vi.mocked(apiClient.post).mockImplementation(never);
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "SERVER_NAME,SERVER_IP,REMOTE_USER,DESCRIPTION" } });
      fireEvent.click(screen.getByRole("button", { name: "Importar" }));
    }],
  ];

  it.each(busyCases)("%s does not close while its request is in flight", async (_name, node, submit, before) => {
    before?.();
    const onClose = vi.fn();
    wrap(node(onClose));
    await submit();
    await vi.waitFor(() => expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true"));
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("side-panel-overlay"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
