import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, Loader2, UserPlus, X } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useClientOpsStatus, useClientOpsText, useDarckwareClients } from "@/hooks/useClientOps";
import { useClientConversionsViewModel, type ClientConversionsViewModel } from "@/hooks/useClientConversionsViewModel";
import { ClientOpsStatusBanner } from "@/pages/client-demands/shared";
import { ConversionDialog } from "./ConversionDialog";
import { DialogShell } from "./ContractFields";

export default function ClientAccountsPage() {
  const { t } = useTranslation("clientOps");
  const { errorText } = useClientOpsText();
  const integration = useClientOpsStatus();
  const clients = useDarckwareClients();
  const vm = useClientConversionsViewModel();
  const [search, setSearch] = useState("");
  const term = search.trim().toLowerCase();
  const visible = (clients.data?.items ?? []).filter(
    (c) => !term || [c.company_name, c.contact_name, c.email].some((v) => v?.toLowerCase().includes(term)),
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("accounts.title")}
        description={t("accounts.description")}
        icon={<Building2 className="h-6 w-6" />}
        actions={
          <Button onClick={vm.openLeadPicker} disabled={!integration.data?.configured}>
            <UserPlus className="mr-2 h-4 w-4" /> {t("conversions.convertLead")}
          </Button>
        }
      />
      <ClientOpsStatusBanner status={integration.data} />

      {vm.lastResult && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
          <span>{t("conversions.done")}</span>
          <Link to="/client-emails" className="underline">
            {t("conversions.openEmails")}
          </Link>
          <Link to={`/client-accounts/${vm.lastResult.client_account_id}`} className="underline">
            {t("conversions.openClient")}
          </Link>
          <button type="button" className="ml-auto" onClick={vm.dismiss} aria-label={t("common.dismiss") }>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {vm.errorMessage && !vm.dialog && (
        <p className="break-words rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {vm.errorMessage}
        </p>
      )}

      <ConversionsPanel vm={vm} />

      <Card>
        <CardContent className="space-y-3 p-4">
          <Input
            placeholder={t("accounts.search")}
            className="max-md:text-base"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {clients.isLoading && <Loader2 className="h-5 w-5 animate-spin" />}
          {clients.isError && <p className="break-words text-sm text-destructive">{errorText(clients.error)}</p>}
          {clients.isSuccess && visible.length === 0 && <p className="text-sm text-muted-foreground">{t("accounts.empty")}</p>}
          <ul className="divide-y">
            {visible.map((c) => (
              <li key={c.id}>
                <Link to={`/client-accounts/${c.id}`} className="block space-y-0.5 py-3 hover:bg-muted/40">
                  <div className="font-medium">{c.company_name}</div>
                  <div className="break-all text-xs text-muted-foreground">
                    {[c.contact_name, c.email].filter(Boolean).join(" · ")}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {vm.status === "picking" && <LeadPicker vm={vm} />}
      {vm.dialog && <ConversionDialog vm={vm} />}
      <ConfirmDialog
        open={Boolean(vm.rejecting)}
        title={t("conversions.rejectTitle")}
        confirmLabel={t("conversions.reject")}
        confirmDisabled={!vm.rejectReason.trim()}
        loading={vm.status === "submitting"}
        onConfirm={() => void vm.confirmReject()}
        onCancel={vm.dismiss}
      >
        <div className="space-y-1">
          <Label htmlFor="conv-reject">{t("conversions.rejectReason")}</Label>
          <Textarea
            id="conv-reject"
            rows={3}
            className="max-md:text-base"
            value={vm.rejectReason}
            onChange={(e) => vm.setRejectReason(e.target.value)}
          />
        </div>
      </ConfirmDialog>
    </div>
  );
}

function ConversionsPanel({ vm }: { vm: ClientConversionsViewModel }) {
  const { t } = useTranslation("clientOps");
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold">{t("conversions.title")}</h2>
          {vm.proposals.length > 0 && <Badge variant="warning">{vm.proposals.length}</Badge>}
        </div>
        {vm.loadError && <p className="break-words text-sm text-destructive">{vm.loadError}</p>}
        {!vm.loadError && vm.status !== "loading" && vm.proposals.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("conversions.empty")}</p>
        )}
        <ul className="space-y-2">
          {vm.proposals.map((p) => (
            <li key={p.id} className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-0.5">
                <div className="font-medium">{p.payload.company_name || p.lead?.company || p.lead?.name}</div>
                <div className="break-all text-xs text-muted-foreground">
                  {[p.payload.contact_name, p.payload.email].filter(Boolean).join(" · ")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t("conversions.proposedBy", { who: p.proposed_by })}
                  {p.payload.contract?.contract_type && ` · ${t(`contract.type.${p.payload.contract.contract_type}`)}`}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => vm.openProposal(p)}>
                  {t("conversions.review")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => vm.requestReject(p)}>
                  {t("conversions.reject")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function LeadPicker({ vm }: { vm: ClientConversionsViewModel }) {
  const { t } = useTranslation("clientOps");
  return (
    <DialogShell title={t("conversions.pickTitle")} onClose={vm.close}>
      <Input
        autoFocus
        placeholder={t("conversions.pickSearch")}
        className="max-md:text-base"
        value={vm.leadSearch}
        onChange={(e) => vm.setLeadSearch(e.target.value)}
      />
      {vm.leadsLoading && <Loader2 className="h-5 w-5 animate-spin" />}
      {!vm.leadsLoading && vm.leads.length === 0 && <p className="text-sm text-muted-foreground">{t("conversions.noLeads")}</p>}
      <ul className="max-h-80 divide-y overflow-y-auto">
        {vm.leads.map((lead) => (
          <li key={lead.id}>
            <button type="button" onClick={() => vm.pickLead(lead)} className="w-full space-y-0.5 py-2 text-left hover:bg-muted/40">
              <div className="font-medium">{lead.company || lead.name}</div>
              <div className="break-all text-xs text-muted-foreground">
                {[lead.name, lead.email, lead.phone].filter(Boolean).join(" · ")}
              </div>
            </button>
          </li>
        ))}
      </ul>
      <div className="flex justify-end">
        <button type="button" className={buttonVariants({ variant: "outline" })} onClick={vm.close}>
          {t("contract.cancel")}
        </button>
      </div>
    </DialogShell>
  );
}
