import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import type { Client } from "@/hooks/useClients";
import type { Workstation } from "@/hooks/useWorkstations";
import type { PeerGrant } from "@/hooks/usePeerGrants";
import type { NexoBuildCatalog, NexoInstallation } from "@/hooks/useNexoInstallations";
import ClientsPage from ".";
import NewClientPage from "./new";
import ClientDetailPage from "./[id]";

const mocks = vi.hoisted(() => ({
  useClients: vi.fn(),
  useClient: vi.fn(),
  createClient: vi.fn(),
  useWorkstations: vi.fn(),
  usePeerGrants: vi.fn(),
  createGrant: vi.fn(),
  revokeGrant: vi.fn(),
  useNexoBuilds: vi.fn(),
  useNexoInstallations: vi.fn(),
  generatePackage: vi.fn(),
  resetPackage: vi.fn(),
  refetchBuilds: vi.fn(),
  refetchInstallations: vi.fn(),
  packagePending: false,
  packageError: null as Error | null,
}));

vi.mock("@/hooks/useClients", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useClients")>();
  return {
    ...actual,
    useClients: mocks.useClients,
    useClient: mocks.useClient,
    useCreateClient: () => ({
      mutate: mocks.createClient,
      isPending: false,
      isError: false,
      error: null,
    }),
  };
});

vi.mock("@/hooks/useWorkstations", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useWorkstations")>();
  return { ...actual, useWorkstations: mocks.useWorkstations };
});

vi.mock("@/hooks/usePeerGrants", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/usePeerGrants")>();
  return {
    ...actual,
    usePeerGrants: mocks.usePeerGrants,
    useCreatePeerGrant: () => ({ mutate: mocks.createGrant, isPending: false, error: null }),
    useRevokePeerGrant: () => ({ mutate: mocks.revokeGrant, isPending: false, error: null }),
  };
});

vi.mock("@/hooks/useNexoInstallations", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useNexoInstallations")>();
  return {
    ...actual,
    useNexoBuilds: mocks.useNexoBuilds,
    useNexoInstallations: mocks.useNexoInstallations,
    useGenerateNexoPackage: () => ({
      mutate: mocks.generatePackage,
      reset: mocks.resetPackage,
      isPending: mocks.packagePending,
      isError: Boolean(mocks.packageError),
      error: mocks.packageError,
    }),
  };
});

const CLIENT: Client = {
  id: "client-1",
  name: "Acme Operations",
  contact_name: "Ana Souza",
  contact_phone: "+55 11 99999-0000",
  contact_email: "ana@acme.test",
  support_plan: "8h",
  notes: "Acesso acompanhado.",
  headscale_tag: "tag:cliente-acme-operations",
  created_at: "2026-09-07T10:00:00Z",
  updated_at: "2026-09-07T12:00:00Z",
};

const workstation = (id: string, hostname: string): Workstation => ({
  id,
  client_id: CLIENT.id,
  hostname,
  os_kind: "linux",
  device_token_issued_at: "2026-09-07T10:00:00Z",
  device_token_revoked_at: null,
  device_token_active: true,
  last_report_at: "2026-09-07T12:00:00Z",
  last_seen_agent_version: "1.0.0",
  created_at: "2026-09-07T10:00:00Z",
  updated_at: "2026-09-07T12:00:00Z",
});

const WORKSTATIONS = [
  workstation("ws-a", "finance-01"),
  workstation("ws-b", "finance-02"),
  workstation("ws-c", "reception-01"),
];

const GRANT: PeerGrant = {
  id: "grant-1",
  workstation_a_id: "ws-b",
  workstation_b_id: "ws-a",
  granted_by_user_id: null,
  granted_at: "2026-09-07T12:00:00Z",
  revoked_at: null,
};

const INSTALLATION: NexoInstallation = {
  id: "installation-1",
  workstation_id: "ws-a",
  client_id: CLIENT.id,
  build_id: "build-linux",
  client_name: CLIENT.name,
  workstation_hostname: "finance-01",
  os_kind: "linux",
  status: "online",
  expected_version: "1.0.0",
  detected_version: "1.0.0",
  package_generated_at: "2026-09-07T11:00:00Z",
  downloaded_at: "2026-09-07T11:01:00Z",
  online_at: "2026-09-07T12:00:00Z",
  last_report_at: "2026-09-07T12:00:00Z",
  last_error: null,
  created_at: "2026-09-07T11:00:00Z",
  updated_at: "2026-09-07T12:00:00Z",
};

const BUILDS: NexoBuildCatalog = {
  source: { git_sha: "a".repeat(40), agent_version: "1.0.0" },
  builds: [{
    id: "build-linux",
    git_sha: "a".repeat(40),
    agent_version: "1.0.0",
    os_kind: "linux",
    status: "ready",
    artifact_size: 1024,
    sha256: "b".repeat(64),
    build_log_excerpt: null,
    started_at: "2026-09-07T10:00:00Z",
    completed_at: "2026-09-07T10:01:00Z",
    created_at: "2026-09-07T10:00:00Z",
    updated_at: "2026-09-07T10:01:00Z",
  }],
};

function renderAt(path: string, element: React.ReactNode, routePath = "*") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Clients pages", () => {
  beforeEach(() => {
    mocks.createClient.mockReset();
    mocks.createGrant.mockReset();
    mocks.revokeGrant.mockReset();
    mocks.generatePackage.mockReset();
    mocks.resetPackage.mockReset();
    mocks.refetchBuilds.mockReset();
    mocks.refetchInstallations.mockReset();
    mocks.packagePending = false;
    mocks.packageError = null;
    mocks.useClients.mockReturnValue({ data: [CLIENT], isLoading: false, isError: false, error: null });
    mocks.useClient.mockReturnValue({ data: CLIENT, isLoading: false, isError: false, error: null });
    mocks.useWorkstations.mockReturnValue({ data: WORKSTATIONS, isLoading: false, isError: false, error: null });
    mocks.usePeerGrants.mockReturnValue({ data: [GRANT], isLoading: false, isError: false, error: null });
    mocks.useNexoBuilds.mockReturnValue({ data: BUILDS, isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds });
    mocks.useNexoInstallations.mockReturnValue({ data: [INSTALLATION], isLoading: false, isError: false, error: null, refetch: mocks.refetchInstallations });
  });

  it("links the registry to a dedicated creation page without rendering a modal", () => {
    renderAt("/clients", <ClientsPage />);

    expect(screen.getByRole("heading", { name: "Clientes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Novo cliente/i })).toHaveAttribute("href", "/clients/new");
    expect(screen.getByRole("link", { name: "Acme Operations" })).toHaveAttribute("href", "/clients/client-1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("submits the dedicated client form with trimmed optional values", () => {
    renderAt("/clients/new", <NewClientPage />);

    fireEvent.change(screen.getByLabelText(/Nome do cliente/i), { target: { value: "  New Co  " } });
    fireEvent.change(screen.getByLabelText(/Nome do contato/i), { target: { value: "  Joana  " } });
    fireEvent.change(screen.getByLabelText(/Plano de suporte/i), { target: { value: "8h" } });
    fireEvent.click(screen.getByRole("button", { name: /Criar cliente/i }));

    expect(mocks.createClient).toHaveBeenCalledWith(
      expect.objectContaining({ name: "New Co", contact_name: "Joana", support_plan: "8h" }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("renders each unordered workstation pair and recognizes a reversed active grant", () => {
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");

    expect(screen.getAllByRole("switch")).toHaveLength(3);
    expect(screen.getByRole("switch", { name: /finance-01.*finance-02/i })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("switch", { name: /finance-01.*reception-01/i })).toHaveAttribute("aria-checked", "false");
  });

  it("grants immediately but confirms revocation before mutating", () => {
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");

    fireEvent.click(screen.getByRole("switch", { name: /finance-01.*reception-01/i }));
    expect(mocks.createGrant).toHaveBeenCalledWith(
      { workstationAId: "ws-a", workstationBId: "ws-c" },
      expect.objectContaining({ onSettled: expect.any(Function) }),
    );

    fireEvent.click(screen.getByRole("switch", { name: /finance-01.*finance-02/i }));
    expect(mocks.revokeGrant).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: /Revogar acesso/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Revogar acesso/i }));
    expect(mocks.revokeGrant).toHaveBeenCalledWith("grant-1", expect.objectContaining({ onSuccess: expect.any(Function) }));
  });

  it("shows installation state and links to filtered history", () => {
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");

    expect(screen.getByText("Online")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ver histórico.*finance-01/i })).toHaveAttribute(
      "href",
      "/nexo-agents?client_id=client-1&workstation_id=ws-a",
    );
    expect(screen.queryByRole("link", { name: /ver histórico.*finance-02/i })).not.toBeInTheDocument();
    expect(screen.getAllByText("Não gerado")).toHaveLength(2);
  });

  it("requires confirmation before generating a workstation package", () => {
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");

    fireEvent.click(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i }));
    expect(mocks.generatePackage).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("token anterior deixará de funcionar");

    fireEvent.click(screen.getByRole("button", { name: /confirmar geração/i }));
    expect(mocks.generatePackage).toHaveBeenCalledWith(
      { workstationId: "ws-a", buildId: "build-linux" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("prefers the current-source ready build and falls back only within the workstation OS", () => {
    mocks.useNexoBuilds.mockReturnValue({
      data: {
        ...BUILDS,
        builds: [
          { ...BUILDS.builds[0], id: "old-linux", git_sha: "c".repeat(40), agent_version: "0.9.0" },
          { ...BUILDS.builds[0], id: "current-windows", os_kind: "windows", git_sha: BUILDS.source.git_sha },
          { ...BUILDS.builds[0], id: "current-linux", git_sha: BUILDS.source.git_sha },
        ],
      },
      isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds,
    });
    const current = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");

    fireEvent.click(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirmar geração/i }));
    expect(mocks.generatePackage).toHaveBeenCalledWith(
      { workstationId: "ws-a", buildId: "current-linux" },
      expect.any(Object),
    );
    current.unmount();

    mocks.generatePackage.mockReset();
    mocks.useNexoBuilds.mockReturnValue({
      data: { ...BUILDS, builds: [
        { ...BUILDS.builds[0], id: "old-linux", git_sha: "c".repeat(40) },
        { ...BUILDS.builds[0], id: "current-windows", os_kind: "windows", git_sha: BUILDS.source.git_sha },
      ] },
      isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds,
    });
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    fireEvent.click(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirmar geração/i }));
    expect(mocks.generatePackage).toHaveBeenCalledWith(
      { workstationId: "ws-a", buildId: "old-linux" },
      expect.any(Object),
    );
  });

  it("distinguishes loading, unavailable, and failed build lookup states", () => {
    mocks.useNexoBuilds.mockReturnValue({ data: undefined, isLoading: true, isError: false, error: null, refetch: mocks.refetchBuilds });
    const loading = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i })).toBeDisabled();
    expect(screen.getAllByText(/carregando builds/i).length).toBeGreaterThan(0);
    loading.unmount();

    mocks.useNexoBuilds.mockReturnValue({ data: { ...BUILDS, builds: [] }, isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds });
    const unavailable = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getAllByText(/build pronta é necessária/i).length).toBeGreaterThan(0);
    unavailable.unmount();

    mocks.useNexoBuilds.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error("offline"), refetch: mocks.refetchBuilds });
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getAllByText(/não foi possível carregar as builds/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(mocks.refetchBuilds).toHaveBeenCalledTimes(1);
  });

  it("keeps installation loading and failure distinct from an uninstalled workstation", () => {
    mocks.useNexoInstallations.mockReturnValue({ data: undefined, isLoading: true, isError: false, error: null, refetch: mocks.refetchInstallations });
    const loading = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getAllByText("Desconhecido")).toHaveLength(3);
    expect(screen.queryByText("Não gerado")).not.toBeInTheDocument();
    loading.unmount();

    mocks.useNexoInstallations.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error("offline"), refetch: mocks.refetchInstallations });
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getByRole("alert")).toHaveTextContent(/status da instalação Nexo/i);
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    expect(mocks.refetchInstallations).toHaveBeenCalledTimes(1);
  });

  it("rejects a cross-OS build and prevents duplicate generation while pending", () => {
    mocks.useNexoBuilds.mockReturnValue({ data: { ...BUILDS, builds: [{ ...BUILDS.builds[0], os_kind: "windows" }] }, isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds });
    const crossOs = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i })).toBeDisabled();
    crossOs.unmount();

    mocks.packagePending = true;
    mocks.useNexoBuilds.mockReturnValue({ data: BUILDS, isLoading: false, isError: false, error: null, refetch: mocks.refetchBuilds });
    renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    expect(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i })).toBeDisabled();
  });

  it("keeps one stable generation error region and clears it when dismissed", () => {
    mocks.packageError = new Error("download failed");
    const view = renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
    fireEvent.click(screen.getByRole("button", { name: /gerar e baixar.*finance-01/i }));

    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByTestId("client-package-feedback")).toHaveClass("min-h-16");
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(mocks.resetPackage).toHaveBeenCalled();

    mocks.packageError = null;
    view.rerender(
      <MemoryRouter initialEntries={["/clients/client-1"]}>
        <Routes><Route path="/clients/:id" element={<ClientDetailPage />} /></Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
