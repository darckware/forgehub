import { useState } from "react";
import {
  useClientOpsText,
  useApproveConversion,
  useConversions,
  useConvertLead,
  useDarckwareLeads,
  useRejectConversion,
  type ContractInput,
  type ConversionInput,
  type ConversionProposal,
  type ConversionResult,
  type DarckwareLead,
} from "@/hooks/useClientOps";

/**
 * ViewModel Hook (§21) for lead → client conversion (2026-10-04, Onda 2).
 *
 * Two ways in, one form: approving what Lara proposed (her payload pre-fills
 * the form, every field still editable), or Marcelo converting a lead himself.
 * Either way Darckware creates client + contact + contract + welcome draft in
 * one transaction; the welcome e-mail still waits in the approval queue.
 */
export type ConversionsStatus = "loading" | "ready" | "picking" | "editing" | "rejecting" | "submitting" | "error";

export type ConversionDialog =
  | { mode: "approve"; proposal: ConversionProposal }
  | { mode: "convert"; lead: DarckwareLead };

export const EMPTY_CONTRACT: ContractInput = {
  contract_type: "suporte_horas",
  plan_name: "",
  billing_cycle_day: 1,
};

/** Form defaults from Lara's proposal or straight from the lead. */
export function conversionDefaults(dialog: ConversionDialog): ConversionInput {
  if (dialog.mode === "approve") {
    const p = dialog.proposal.payload;
    return {
      company_name: p.company_name ?? "",
      contact_name: p.contact_name ?? "",
      email: p.email ?? "",
      phone: p.phone ?? "",
      department: p.department ?? "",
      existing_client_account_id: "",
      contract: { ...EMPTY_CONTRACT, ...(p.contract ?? {}) } as ContractInput,
    };
  }
  const lead = dialog.lead;
  return {
    company_name: lead.company ?? "",
    contact_name: lead.name ?? "",
    email: lead.email ?? "",
    phone: lead.phone ?? "",
    department: "",
    existing_client_account_id: "",
    contract: { ...EMPTY_CONTRACT },
  };
}

export interface ClientConversionsViewModel {
  status: ConversionsStatus;
  proposals: ConversionProposal[];
  loadError?: string;
  dialog?: ConversionDialog;
  leadSearch: string;
  leads: DarckwareLead[];
  leadsLoading: boolean;
  rejecting?: ConversionProposal;
  rejectReason: string;
  notes: string;
  errorMessage?: string;
  lastResult?: ConversionResult;
  openLeadPicker(): void;
  setLeadSearch(search: string): void;
  pickLead(lead: DarckwareLead): void;
  openProposal(proposal: ConversionProposal): void;
  setNotes(notes: string): void;
  close(): void;
  submit(input: ConversionInput): Promise<void>;
  requestReject(proposal: ConversionProposal): void;
  setRejectReason(reason: string): void;
  confirmReject(): Promise<void>;
  dismiss(): void;
}

export function useClientConversionsViewModel(): ClientConversionsViewModel {
  const { errorText } = useClientOpsText();
  const [picking, setPicking] = useState(false);
  const [leadSearch, setLeadSearch] = useState("");
  const [dialog, setDialog] = useState<ConversionDialog>();
  const [rejecting, setRejecting] = useState<ConversionProposal>();
  const [rejectReason, setRejectReason] = useState("");
  const [notes, setNotes] = useState("");
  const [errorMessage, setErrorMessage] = useState<string>();
  const [lastResult, setLastResult] = useState<ConversionResult>();

  const proposals = useConversions("proposta");
  const leads = useDarckwareLeads(leadSearch, picking);
  const approve = useApproveConversion();
  const convert = useConvertLead();
  const reject = useRejectConversion();

  let status: ConversionsStatus;
  if (approve.isPending || convert.isPending || reject.isPending) status = "submitting";
  else if (dialog) status = "editing";
  else if (rejecting) status = "rejecting";
  else if (picking) status = "picking";
  else if (errorMessage) status = "error";
  else if (proposals.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    proposals: proposals.data?.items ?? [],
    loadError: proposals.isError ? errorText(proposals.error) : undefined,
    dialog,
    leadSearch,
    // A lead already turned into a client is not offered again.
    leads: (leads.data?.leads ?? []).filter((lead) => !lead.client_account_id),
    leadsLoading: leads.isLoading && picking,
    rejecting,
    rejectReason,
    notes,
    errorMessage,
    lastResult,
    openLeadPicker() {
      setErrorMessage(undefined);
      setPicking(true);
    },
    setLeadSearch,
    pickLead(lead) {
      setPicking(false);
      setNotes("");
      setDialog({ mode: "convert", lead });
    },
    openProposal(proposal) {
      setErrorMessage(undefined);
      setDialog({ mode: "approve", proposal });
    },
    setNotes,
    close() {
      setDialog(undefined);
      setPicking(false);
      setErrorMessage(undefined);
    },
    async submit(input) {
      if (!dialog) return;
      setErrorMessage(undefined);
      try {
        const result =
          dialog.mode === "approve"
            ? await approve.mutateAsync({ id: dialog.proposal.id, input })
            : await convert.mutateAsync({ leadId: dialog.lead.id, input, notes });
        setLastResult(result);
        setDialog(undefined);
      } catch (error) {
        // The dialog stays open with what was typed: a 409 (e-mail already a
        // client) is fixed by linking to that client, not by retyping.
        setErrorMessage(errorText(error));
      }
    },
    requestReject(proposal) {
      setRejectReason("");
      setRejecting(proposal);
    },
    setRejectReason,
    async confirmReject() {
      if (!rejecting || !rejectReason.trim()) return;
      try {
        await reject.mutateAsync({ id: rejecting.id, reason: rejectReason.trim() });
        setRejecting(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
        setRejecting(undefined);
      }
    },
    dismiss() {
      setErrorMessage(undefined);
      setRejecting(undefined);
      setLastResult(undefined);
    },
  };
}
