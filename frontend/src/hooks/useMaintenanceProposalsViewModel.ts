import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface MaintenanceProposal {
  id: string; agent_id: string; message_number: number; content_hash: string;
  content: string; shell: string; risk: string; timeout_seconds: number;
  requires_elevation: boolean; reason: string; expected_effect: string; rollback: string;
  status: string; expires_at: string | null; decision_reason: string | null;
  machines: {id: string; name: string}[];
  parameters: {name: string; vault_secret: string; vault_field?: string}[];
}

export function useMaintenanceProposalsViewModel() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["maintenance-proposals"], queryFn: () => apiClient.get<MaintenanceProposal[]>("/api/v1/maintenance-proposals"), refetchInterval: 15000 });
  const [selected, setSelected] = useState<MaintenanceProposal | null>(null);
  const [decision, setDecision] = useState<"approved" | "rejected">("approved");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const gate = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const status = busy ? "submitting" : error || query.isError ? "error" : query.isLoading ? "loading" : selected ? "reviewing" : "idle";
  return {status, proposals: query.data ?? [], selected, decision, reason, setReason,
    error: error ?? (query.error?.message || null),
    refresh: () => void query.refetch(),
    review: (p: MaintenanceProposal, action: "approved" | "rejected") => {setSelected(p);setDecision(action);setReason("");setError(null);},
    close: () => {if (!gate.current) {setSelected(null);setError(null);}},
    confirm: async () => {
      if (!selected || gate.current || (decision === "rejected" && !reason.trim())) return;
      gate.current = true; setBusy(true); setError(null);
      try {
        await apiClient.post(`/api/v1/maintenance-proposals/${selected.id}/decision`, {decision, content_hash: selected.content_hash, reason: reason.trim() || null});
        setSelected(null); await qc.invalidateQueries({queryKey: ["maintenance-proposals"]});
      } catch (e) {setError((e as Error).message);}
      finally {gate.current = false;setBusy(false);}
    },
  };
}
