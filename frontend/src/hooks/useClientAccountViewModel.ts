import { useState } from "react";
import {
  useClientOpsText,
  useClientEmails,
  useClientFactory,
  useWorkItems,
  useCreateContract,
  useGenerateMonthlyReport,
  useLinkProduct,
  useDarckwareClient,
  useUpdateContract,
  type ClientFactory,
  type ClientSummary,
  type Contract,
  type ContractInput,
  type ContractStatus,
  type MonthlyReportResult,
  type OutboundEmail,
  type WorkItem,
} from "@/hooks/useClientOps";

/**
 * ViewModel Hook (§21) for one Darckware client's file (2026-10-04, Onda 2):
 * contacts, contracts and open work. Contract writes are commercial decisions
 * and go through ForgeHub's approver credential; a status change (suspend,
 * close, reactivate) always asks for confirmation first.
 */
const PRIORITY_RANK: Record<string, number> = { urgente: 0, alta: 1, media: 2, baixa: 3 };

export type ClientAccountStatus = "loading" | "ready" | "editing" | "confirming" | "submitting" | "error";

export type ContractDialog = { mode: "create" } | { mode: "edit"; contract: Contract };

export function contractDefaults(contract?: Contract): ContractInput {
  if (!contract) return { contract_type: "suporte_horas", plan_name: "", billing_cycle_day: 1 };
  return {
    contract_type: contract.contract_type,
    plan_name: contract.plan_name,
    monthly_hours_quota: contract.monthly_hours_quota ?? undefined,
    monthly_price: contract.monthly_price ?? undefined,
    extra_hour_rate: contract.extra_hour_rate ?? undefined,
    billing_cycle_day: contract.billing_cycle_day ?? undefined,
    start_date: contract.start_date ?? "",
    end_date: contract.end_date ?? "",
    total_value: contract.total_value ?? undefined,
    scope_summary: contract.scope_summary ?? "",
    document_url: contract.document_url ?? "",
  };
}

export interface ClientAccountViewModel {
  status: ClientAccountStatus;
  client?: ClientSummary;
  loadError?: string;
  contractDialog?: ContractDialog;
  statusChange?: { contract: Contract; status: ContractStatus };
  errorMessage?: string;
  /** Tickets and demands still open for this client -- the work to resolve. */
  openWork: WorkItem[];
  openWorkLoading: boolean;
  /** E-mails to this client (any status), newest first; reports are those with kind informe_mensal. */
  emails: OutboundEmail[];
  reports: OutboundEmail[];
  /** This client's products/projects in the Software Factory (Onda 3). */
  factory?: ClientFactory;
  linkProductId: string;
  linking: boolean;
  setLinkProductId(id: string): void;
  linkProduct(): Promise<void>;
  reportPending: boolean;
  reportResult?: MonthlyReportResult;
  generateReport(): Promise<void>;
  openCreateContract(): void;
  openEditContract(contract: Contract): void;
  closeContract(): void;
  submitContract(input: ContractInput): Promise<void>;
  requestStatusChange(contract: Contract, status: ContractStatus): void;
  cancelStatusChange(): void;
  confirmStatusChange(): Promise<void>;
  dismiss(): void;
}

export function useClientAccountViewModel(clientId?: string): ClientAccountViewModel {
  const { errorText } = useClientOpsText();
  const [contractDialog, setContractDialog] = useState<ContractDialog>();
  const [statusChange, setStatusChange] = useState<{ contract: Contract; status: ContractStatus }>();
  const [errorMessage, setErrorMessage] = useState<string>();

  const query = useDarckwareClient(clientId);
  const create = useCreateContract();
  const update = useUpdateContract();
  const factory = useClientFactory(clientId);
  const openWork = useWorkItems({ client_account_id: clientId, stage: "open" }, Boolean(clientId));
  const emails = useClientEmails(clientId);
  const allEmails = emails.data?.items ?? [];
  const link = useLinkProduct();
  const [linkProductId, setLinkProductId] = useState("");
  const report = useGenerateMonthlyReport();
  const [reportResult, setReportResult] = useState<MonthlyReportResult>();

  let status: ClientAccountStatus;
  if (create.isPending || update.isPending) status = "submitting";
  else if (contractDialog) status = "editing";
  else if (statusChange) status = "confirming";
  else if (errorMessage) status = "error";
  else if (query.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    client: query.data,
    loadError: query.isError ? errorText(query.error) : undefined,
    contractDialog,
    statusChange,
    errorMessage,
    // Most urgent first, then oldest: what to resolve next is at the top.
    openWork: [...(openWork.data?.items ?? [])].sort(
      (a, b) => (PRIORITY_RANK[a.priority ?? ""] ?? 9) - (PRIORITY_RANK[b.priority ?? ""] ?? 9) || (a.created_at ?? "").localeCompare(b.created_at ?? ""),
    ),
    openWorkLoading: openWork.isLoading,
    emails: allEmails.filter((e) => e.kind !== "informe_mensal"),
    reports: allEmails.filter((e) => e.kind === "informe_mensal"),
    factory: factory.data,
    linkProductId,
    linking: link.isPending,
    setLinkProductId,
    async linkProduct() {
      if (!clientId || !linkProductId) return;
      setErrorMessage(undefined);
      try {
        await link.mutateAsync({ clientId, productId: linkProductId });
        setLinkProductId("");
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    reportPending: report.isPending,
    reportResult,
    async generateReport() {
      if (!clientId) return;
      setErrorMessage(undefined);
      try {
        setReportResult(await report.mutateAsync({ clientId }));
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    openCreateContract() {
      setErrorMessage(undefined);
      setContractDialog({ mode: "create" });
    },
    openEditContract(contract) {
      setErrorMessage(undefined);
      setContractDialog({ mode: "edit", contract });
    },
    closeContract() {
      setContractDialog(undefined);
      setErrorMessage(undefined);
    },
    async submitContract(input) {
      if (!clientId || !contractDialog) return;
      setErrorMessage(undefined);
      try {
        if (contractDialog.mode === "create") {
          await create.mutateAsync({ clientId, input });
        } else {
          // The type is fixed once created; only the terms change.
          const { contract_type: _type, ...changes } = input;
          await update.mutateAsync({ id: contractDialog.contract.id, changes });
        }
        setContractDialog(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    requestStatusChange(contract, next) {
      setErrorMessage(undefined);
      setStatusChange({ contract, status: next });
    },
    cancelStatusChange: () => setStatusChange(undefined),
    async confirmStatusChange() {
      if (!statusChange) return;
      try {
        await update.mutateAsync({ id: statusChange.contract.id, changes: { status: statusChange.status } });
      } catch (error) {
        setErrorMessage(errorText(error));
      } finally {
        setStatusChange(undefined);
      }
    },
    dismiss: () => setErrorMessage(undefined),
  };
}
