import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Agentes e MCP do ForgeHub (business rules MCP-005, MCP-023): which ForgeHub MCP servers each
 * agent gets, and whether a container restart / direct database query runs at once or goes to
 * Marcelo's approval. Messages (`forgehub`) is always on and not part of the editable list. */

export type ActionMode = "direct" | "approval";

export interface AgentMcpAccessRow {
  agent_id: string;
  name: string;
  profile_slug: string | null;
  department: string | null;
  runtime_type: string | null;
  core_server: string;
  servers: string[];
  restart_mode: ActionMode;
  query_mode: ActionMode;
  personal_allowed: boolean;
  saved: boolean;
  suggested: { servers: string[]; restart_mode: ActionMode; query_mode: ActionMode };
  updated_by: string | null;
  updated_at: string | null;
}

export interface AgentMcpAccessCatalog {
  core_server: string;
  servers: string[];
  agents: AgentMcpAccessRow[];
}

export interface AgentMcpAccessDraft {
  servers: string[];
  restart_mode: ActionMode;
  query_mode: ActionMode;
}

export type AgentMcpAccessStatus = "loading" | "ready" | "error";

export interface AgentMcpAccessViewModel {
  status: AgentMcpAccessStatus;
  servers: string[];
  coreServer: string;
  rows: AgentMcpAccessRow[];
  draftOf: (row: AgentMcpAccessRow) => AgentMcpAccessDraft;
  isDirty: (row: AgentMcpAccessRow) => boolean;
  toggleServer: (row: AgentMcpAccessRow, server: string) => void;
  setMode: (row: AgentMcpAccessRow, field: "restart_mode" | "query_mode", mode: ActionMode) => void;
  applySuggestion: (row: AgentMcpAccessRow) => void;
  discard: (row: AgentMcpAccessRow) => void;
  save: (row: AgentMcpAccessRow) => void;
  savingId: string | null;
  saveError: { agentId: string; message: string } | null;
}

export const MCP_ACCESS_KEY = ["mcp-access"];

function sameDraft(a: AgentMcpAccessDraft, b: AgentMcpAccessDraft) {
  return (
    a.restart_mode === b.restart_mode &&
    a.query_mode === b.query_mode &&
    [...a.servers].sort().join() === [...b.servers].sort().join()
  );
}

export function useAgentMcpAccessViewModel(): AgentMcpAccessViewModel {
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, AgentMcpAccessDraft>>({});
  const [saveError, setSaveError] = useState<{ agentId: string; message: string } | null>(null);
  const catalog = useQuery({
    queryKey: MCP_ACCESS_KEY,
    queryFn: () => apiClient.get<AgentMcpAccessCatalog>("/api/v1/mcp-access"),
  });

  const stored = (row: AgentMcpAccessRow): AgentMcpAccessDraft => ({
    servers: row.servers,
    restart_mode: row.restart_mode,
    query_mode: row.query_mode,
  });
  const draftOf = (row: AgentMcpAccessRow) => drafts[row.agent_id] ?? stored(row);
  const update = (row: AgentMcpAccessRow, change: Partial<AgentMcpAccessDraft>) =>
    setDrafts((current) => ({ ...current, [row.agent_id]: { ...draftOf(row), ...change } }));

  const mutation = useMutation({
    mutationFn: (row: AgentMcpAccessRow) =>
      apiClient.put<AgentMcpAccessRow>(`/api/v1/mcp-access/${row.agent_id}`, {
        ...draftOf(row),
        expected_updated_at: row.updated_at,
      }),
    onMutate: () => setSaveError(null),
    onSuccess: (_saved, row) => {
      setDrafts((current) => {
        const next = { ...current };
        delete next[row.agent_id];
        return next;
      });
      return queryClient.invalidateQueries({ queryKey: MCP_ACCESS_KEY });
    },
    onError: (error, row) =>
      setSaveError({ agentId: row.agent_id, message: error instanceof Error ? error.message : String(error) }),
  });

  return {
    status: catalog.isLoading ? "loading" : catalog.isError || !catalog.data ? "error" : "ready",
    servers: catalog.data?.servers ?? [],
    coreServer: catalog.data?.core_server ?? "forgehub",
    rows: catalog.data?.agents ?? [],
    draftOf,
    isDirty: (row) => !row.saved || !sameDraft(draftOf(row), stored(row)),
    toggleServer: (row, server) => {
      const current = draftOf(row).servers;
      update(row, { servers: current.includes(server) ? current.filter((s) => s !== server) : [...current, server] });
    },
    setMode: (row, field, mode) => update(row, { [field]: mode }),
    applySuggestion: (row) =>
      update(row, {
        servers: row.suggested.servers.filter((s) => s !== "forgehub_personal" || row.personal_allowed),
        restart_mode: row.suggested.restart_mode,
        query_mode: row.suggested.query_mode,
      }),
    discard: (row) =>
      setDrafts((current) => {
        const next = { ...current };
        delete next[row.agent_id];
        return next;
      }),
    save: (row) => mutation.mutate(row),
    savingId: mutation.isPending ? (mutation.variables?.agent_id ?? null) : null,
    saveError,
  };
}
