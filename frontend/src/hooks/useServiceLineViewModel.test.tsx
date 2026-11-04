import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import { useServiceLineViewModel } from "./useServiceLineViewModel";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));

it("edits a line and converts each list and the SLA for the API", async () => {
  const line = { id: "1", slug: "support", name: "Support", is_active: true, description: null,
    stages: ["Triage"], required_documents: [], evidence_types: ["file:"], default_agents: ["lara"],
    sla_hours: 8, darckware_contract_type: null, client_visible: false };
  vi.mocked(apiClient.get).mockResolvedValue([line]);
  vi.mocked(apiClient.patch).mockResolvedValue(line);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useServiceLineViewModel(), { wrapper });
  await waitFor(() => expect(result.current.lines.data).toHaveLength(1));
  act(() => result.current.edit(line));
  expect(result.current.form.getValues("stages")).toBe("Triage");
  act(() => { result.current.form.setValue("stages", "Triage\nResolve\n"); result.current.form.setValue("sla_hours", "12"); });
  await act(async () => result.current.save.mutateAsync(result.current.form.getValues()));
  expect(apiClient.patch).toHaveBeenCalledWith("/api/v1/service-lines/1", expect.objectContaining({ stages: ["Triage", "Resolve"], sla_hours: 12 }));
});
