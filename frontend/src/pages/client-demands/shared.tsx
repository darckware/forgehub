import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import type { ClientOpsStatus } from "@/hooks/useClientOps";

type BadgeVariant = "default" | "secondary" | "destructive" | "outline" | "success" | "warning";

/** Explicit map -- an unknown status degrades to "outline", never to green. */
const EMAIL_STATUS_VARIANT: Record<string, BadgeVariant> = {
  rascunho: "outline",
  aguardando_aprovacao: "warning",
  aprovado: "secondary",
  enviando: "secondary",
  enviado: "success",
  falhou: "destructive",
  envio_incerto: "destructive",
  rejeitado: "outline",
  cancelado: "outline",
};

export function emailStatusVariant(status: string): BadgeVariant {
  return EMAIL_STATUS_VARIANT[status] ?? "outline";
}

const STAGE_VARIANT: Record<string, BadgeVariant> = {
  novo: "warning",
  em_andamento: "secondary",
  aguardando_cliente: "outline",
  resolvido: "success",
  fechado: "outline",
};

export function stageVariant(stage: string): BadgeVariant {
  return STAGE_VARIANT[stage] ?? "outline";
}

/** Says why the screen is empty when the Darckware side is missing or down. */
export function ClientOpsStatusBanner({ status }: { status?: ClientOpsStatus }) {
  const { t } = useTranslation("clientOps");
  if (!status) return null;
  let message: string | undefined;
  if (!status.configured) message = t("notConfigured");
  else if (!status.reachable) message = t("unreachable", { error: status.error ?? "" });
  else if (status.approver_configured === false) message = t("approverMissing");
  if (!message) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
      <span className="break-words">{message}</span>
    </div>
  );
}
