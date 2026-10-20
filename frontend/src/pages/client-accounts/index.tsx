import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Building2, Loader2, Plus, UserPlus, X } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  useClientOpsStatus,
  useClientOpsText,
  useDarckwareClients,
  useLeadList,
  useRegistrations,
  type DarckwareLead,
} from "@/hooks/useClientOps";
import { useClientProfileViewModel, type ClientProfileViewModel } from "@/hooks/useClientProfileViewModel";
import { useClientConversionsViewModel, type ClientConversionsViewModel } from "@/hooks/useClientConversionsViewModel";
import { ClientOpsStatusBanner } from "@/pages/client-demands/shared";
import { ClientDialog } from "./ClientDialog";
import { ConversionDialog } from "./ConversionDialog";
import { DialogShell } from "./ContractFields";

export default function ClientAccountsPage() {
  const { t } = useTranslation("clientOps");
  const { errorText } = useClientOpsText();
  const integration = useClientOpsStatus();
  const clients = useDarckwareClients(true);
  const vm = useClientConversionsViewModel();
  const profile = useClientProfileViewModel();
  const [tab, setTab] = useState("clients");
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
          <>
            <Button variant="outline" onClick={vm.openLeadPicker} disabled={!integration.data?.configured}>
              <UserPlus className="mr-2 h-4 w-4" /> {t("conversions.convertLead")}
            </Button>
            <Button onClick={profile.openCreate} disabled={!integration.data?.configured}>
              <Plus className="mr-2 h-4 w-4" /> {t("client.new")}
            </Button>
          </>
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
      {profile.createdId && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
          <span>{t("client.created")}</span>
          <Link to={`/client-accounts/${profile.createdId}`} className="underline">
            {t("conversions.openClient")}
          </Link>
        </div>
      )}
      {profile.errorMessage && !profile.dialog && (
        <p className="break-words rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {profile.errorMessage}
        </p>
      )}
      {vm.errorMessage && !vm.dialog && (
        <p className="break-words rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {vm.errorMessage}
        </p>
      )}

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="clients">{t("accounts.tabClients")}</TabsTrigger>
          <TabsTrigger value="leads">
            {t("leads.tab")}
            {vm.proposals.length > 0 && (
              <Badge variant="warning" className="ml-2">
                {vm.proposals.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="clients" className="space-y-4">
          <RegistrationsPanel profile={profile} />
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
                      <div className="flex flex-wrap items-center gap-2 font-medium">
                        {c.company_name}
                        {c.is_active === false && <Badge variant="outline">{t("client.inactive")}</Badge>}
                      </div>
                      <div className="break-all text-xs text-muted-foreground">
                        {[c.contact_name, c.email].filter(Boolean).join(" · ")}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="leads" className="space-y-4">
          <ConversionsPanel vm={vm} />
          <LeadsPanel onConvert={vm.pickLead} />
        </TabsContent>
      </Tabs>

      {vm.status === "picking" && <LeadPicker vm={vm} />}
      {vm.dialog && <ConversionDialog vm={vm} />}
      {profile.dialog && <ClientDialog vm={profile} />}
      <ConfirmDialog
        open={Boolean(profile.rejecting)}
        title={t("registrations.rejectTitle")}
        confirmLabel={t("registrations.reject")}
        confirmDisabled={!profile.rejectReason.trim()}
        loading={profile.status === "submitting"}
        onConfirm={() => void profile.confirmReject()}
        onCancel={profile.cancelReject}
      >
        <div className="space-y-1">
          <Label htmlFor="reg-reject">{t("registrations.rejectReason")}</Label>
          <Textarea
            id="reg-reject"
            rows={3}
            className="max-md:text-base"
            value={profile.rejectReason}
            onChange={(e) => profile.setRejectReason(e.target.value)}
          />
        </div>
      </ConfirmDialog>
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

/** Cadastros que os agentes pediram (2026-10-06): só viram cliente com a aprovação do Marcelo. */
function RegistrationsPanel({ profile }: { profile: ClientProfileViewModel }) {
  const { t } = useTranslation("clientOps");
  const registrations = useRegistrations();
  const items = registrations.data?.items ?? [];
  if (!items.length) return null;
  return (
    <Card className="border-amber-500/40">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">{t("registrations.title")}</h2>
          <Badge variant="warning">{items.length}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{t("registrations.explain")}</p>
        <ul className="divide-y">
          {items.map((r) => (
            <li key={r.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-0.5">
                <div className="font-medium">{r.payload.company_name}</div>
                <div className="break-all text-xs text-muted-foreground">
                  {[r.payload.contact_name, r.payload.email, r.payload.cnpj].filter(Boolean).join(" · ")}
                </div>
                <div className="text-xs text-muted-foreground">{t("registrations.proposedBy", { who: r.proposed_by })}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => profile.openApprove(r)}>
                  {t("registrations.review")}
                </Button>
                <Button size="sm" variant="outline" onClick={() => profile.requestReject(r)}>
                  {t("registrations.reject")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
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

const LEAD_STATUS_VARIANT: Record<string, "success" | "warning" | "outline" | "destructive"> = {
  ganho: "success",
  oportunidade: "warning",
  qualificado: "warning",
  proposta_em_analise: "warning",
  encaminhado_marcelo: "warning",
  perdido: "outline",
  descartado: "outline",
};

/**
 * Every lead Lara (or the site) registered, newest first (2026-10-05, Marcelo:
 * "preciso ver os leads que a Lara cria"). A lead not yet a client can be
 * converted here once the contract is defined; Lara's own route only proposes,
 * and her proposals wait above for approval.
 */
function LeadsPanel({ onConvert }: { onConvert(lead: DarckwareLead): void }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const [search, setSearch] = useState("");
  const [showClosed, setShowClosed] = useState(false);
  const leads = useLeadList(search.trim());
  const closed = (l: DarckwareLead) => Boolean(l.archived_at) || l.commercial_status === "perdido" || l.commercial_status === "descartado";
  const items = (leads.data?.leads ?? []).filter((l) => showClosed || !closed(l));
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="font-semibold">{t("leads.title")}</h2>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
            {t("leads.showClosed")}
          </label>
        </div>
        <Input
          placeholder={t("conversions.pickSearch")}
          className="max-md:text-base"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {leads.isLoading && <Loader2 className="h-5 w-5 animate-spin" />}
        {leads.isError && <p className="break-words text-sm text-destructive">{fmt.errorText(leads.error)}</p>}
        {leads.isSuccess && items.length === 0 && <p className="text-sm text-muted-foreground">{t("conversions.noLeads")}</p>}
        <ul className="divide-y">
          {items.map((lead) => (
            <li key={lead.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{lead.company || lead.name || "—"}</span>
                  {lead.commercial_status && (
                    <Badge variant={LEAD_STATUS_VARIANT[lead.commercial_status] ?? "outline"}>
                      {t(`leads.status.${lead.commercial_status}`, { defaultValue: lead.commercial_status })}
                    </Badge>
                  )}
                </div>
                <div className="break-all text-xs text-muted-foreground">
                  {[lead.company ? lead.name : null, lead.email, lead.phone].filter(Boolean).join(" · ")}
                </div>
                {lead.need_summary && <p className="line-clamp-2 break-words text-sm">{lead.need_summary}</p>}
                <div className="text-xs text-muted-foreground">
                  {[lead.origin, lead.created_at ? fmt.date(lead.created_at) : null].filter(Boolean).join(" · ")}
                  {lead.next_step && ` · ${t("leads.nextStep")}: ${lead.next_step}`}
                </div>
              </div>
              <div className="shrink-0">
                {lead.client_account_id ? (
                  <Link to={`/client-accounts/${lead.client_account_id}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                    {t("leads.isClient")}
                  </Link>
                ) : (
                  !closed(lead) && (
                    <Button size="sm" onClick={() => onConvert(lead)}>
                      {t("conversions.convert")}
                    </Button>
                  )
                )}
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
