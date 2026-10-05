import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Building2, FileText, FolderKanban, Loader2, Pencil, Plus } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { clientDemandsLink, type Contract, type ContractStatus, type OutboundEmail } from "@/hooks/useClientOps";
import { emailStatusVariant, stageVariant } from "@/pages/client-demands/shared";
import { useClientAccountViewModel, type ClientAccountViewModel } from "@/hooks/useClientAccountViewModel";
import { ContractDialog } from "./ContractDialog";

/** Next statuses offered from each status -- explicit, no "anything goes". */
const NEXT_STATUS: Record<ContractStatus, ContractStatus[]> = {
  ativo: ["suspenso", "encerrado"],
  suspenso: ["ativo", "encerrado"],
  encerrado: ["ativo"],
};

const STATUS_VARIANT: Record<ContractStatus, "success" | "warning" | "outline"> = {
  ativo: "success",
  suspenso: "warning",
  encerrado: "outline",
};

function money(value?: number | null) {
  return value == null ? "—" : value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function ClientAccountPage() {
  const { id } = useParams();
  const { t } = useTranslation("clientOps");
  const vm = useClientAccountViewModel(id);
  const client = vm.client;

  return (
    <div className="space-y-4">
      <Link to="/client-accounts" className="inline-flex items-center gap-1 text-sm text-muted-foreground">
        <ArrowLeft className="h-4 w-4" /> {t("accounts.back")}
      </Link>
      {vm.status === "loading" && <Loader2 className="h-5 w-5 animate-spin" />}
      {vm.loadError && <p className="break-words text-sm text-destructive">{vm.loadError}</p>}
      {client && (
        <>
          <PageHeader
            title={client.company_name}
            description={[client.contact_name, client.email].filter(Boolean).join(" · ")}
            icon={<Building2 className="h-6 w-6" />}
            actions={
              <>
                <Link to={clientDemandsLink(client.id)} className={buttonVariants({ variant: "outline" })}>
                  {t("accounts.seeDemands")}
                </Link>
                <Button variant="outline" onClick={() => void vm.generateReport()} disabled={vm.reportPending}>
                  {vm.reportPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileText className="mr-2 h-4 w-4" />}
                  {t("report.generate")}
                </Button>
              </>
            }
          />
          {vm.reportResult && (
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
              <span>
                {vm.reportResult.created
                  ? t("report.generated", { start: vm.reportResult.cycle.start, end: vm.reportResult.cycle.end })
                  : t("report.exists")}
              </span>
              <Link to="/client-emails" className="underline">
                {t("report.open")}
              </Link>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label={t("accounts.openTickets")} value={client.open_tickets} />
            <Stat label={t("accounts.openDemands")} value={client.open_demands} />
          </div>

          {vm.errorMessage && !vm.contractDialog && (
            <p className="break-words rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {vm.errorMessage}
            </p>
          )}

          <OpenWorkSection vm={vm} clientId={client.id} />

          <Card>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="font-semibold">{t("accounts.contracts")}</h2>
                <Button size="sm" onClick={vm.openCreateContract}>
                  <Plus className="mr-2 h-4 w-4" /> {t("accounts.newContract")}
                </Button>
              </div>
              {client.contracts.length === 0 && <p className="text-sm text-muted-foreground">{t("accounts.noContracts")}</p>}
              <ul className="space-y-2">
                {client.contracts.map((c) => (
                  <ContractRow key={c.id} contract={c} vm={vm} />
                ))}
              </ul>
            </CardContent>
          </Card>

          <FactorySection vm={vm} />

          <EmailsSection title={t("accounts.emailsTitle")} empty={t("accounts.noEmails")} emails={vm.emails} />
          <EmailsSection title={t("accounts.reportsTitle")} empty={t("accounts.noReports")} emails={vm.reports} />

          <Card>
            <CardContent className="space-y-3 p-4">
              <h2 className="font-semibold">{t("accounts.contacts")}</h2>
              <ul className="divide-y">
                {client.contacts.map((c) => (
                  <li key={c.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="font-medium">
                        {c.name} <span className="text-xs text-muted-foreground">· {c.department}</span>
                      </div>
                      <div className="break-all text-xs text-muted-foreground">{[c.email, c.phone].filter(Boolean).join(" · ")}</div>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {c.is_primary && <Badge variant="outline">{t("accounts.primary")}</Badge>}
                      <Badge variant={c.is_authorized ? "success" : "warning"}>
                        {t(c.is_authorized ? "accounts.authorized" : "accounts.notAuthorized")}
                      </Badge>
                    </div>
                  </li>
                ))}
              </ul>
              {client.converted_from_leads.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {t("accounts.convertedFrom")}: {client.converted_from_leads.map((l) => l.name).join(", ")}
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {vm.contractDialog && <ContractDialog vm={vm} />}
      <ConfirmDialog
        open={Boolean(vm.statusChange)}
        variant={vm.statusChange?.status === "encerrado" ? "destructive" : "default"}
        icon="warning"
        title={t("accounts.confirmStatusTitle")}
        description={
          vm.statusChange
            ? t("accounts.confirmStatusBody", {
                plan: vm.statusChange.contract.plan_name,
                status: t(`contract.status.${vm.statusChange.status}`).toLowerCase(),
              })
            : undefined
        }
        confirmLabel={vm.statusChange ? t(`accounts.changeStatus.${vm.statusChange.status}`) : undefined}
        loading={vm.status === "submitting"}
        onConfirm={() => void vm.confirmStatusChange()}
        onCancel={vm.cancelStatusChange}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-2xl font-semibold">{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

function ContractRow({ contract: c, vm }: { contract: Contract; vm: ClientAccountViewModel }) {
  const { t } = useTranslation("clientOps");
  return (
    <li className="space-y-2 rounded-md border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{c.plan_name}</span>
            <Badge variant="outline">{t(`contract.type.${c.contract_type}`)}</Badge>
            <Badge variant={STATUS_VARIANT[c.status] ?? "outline"}>{t(`contract.status.${c.status}`, c.status)}</Badge>
          </div>
          <div className="text-sm text-muted-foreground">
            {c.contract_type === "suporte_horas"
              ? `${c.monthly_hours_quota ?? "—"} h/mês · ${money(c.monthly_price)} · ${t("contract.fields.billing_cycle_day")}: ${c.billing_cycle_day ?? "—"}`
              : `${money(c.total_value)}${c.scope_summary ? ` · ${c.scope_summary}` : ""}`}
          </div>
          {c.hours_used_current_cycle !== undefined && (
            <div className="text-xs text-muted-foreground">
              {t("accounts.hoursCycle", { used: c.hours_used_current_cycle, quota: c.monthly_hours_quota, extra: c.extra_hours ?? 0 })}
            </div>
          )}
          {(c.start_date || c.end_date) && (
            <div className="text-xs text-muted-foreground">
              {c.start_date ?? "…"} → {c.end_date ?? "…"}
            </div>
          )}
          {c.document_url && (
            <a href={c.document_url} target="_blank" rel="noreferrer" className="break-all text-xs underline">
              {c.document_url}
            </a>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => vm.openEditContract(c)}>
            <Pencil className="mr-1 h-3 w-3" /> {t("accounts.editContract")}
          </Button>
          {NEXT_STATUS[c.status]?.map((next) => (
            <Button key={next} size="sm" variant="ghost" onClick={() => vm.requestStatusChange(c, next)}>
              {t(`accounts.changeStatus.${next}`)}
            </Button>
          ))}
        </div>
      </div>
    </li>
  );
}

function FactorySection({ vm }: { vm: ClientAccountViewModel }) {
  const { t } = useTranslation("clientOps");
  const factory = vm.factory;
  if (!factory) return null;
  const empty = factory.products.length === 0 && factory.projects.length === 0;
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <h2 className="flex items-center gap-2 font-semibold">
          <FolderKanban className="h-4 w-4" /> {t("factory.title")}
        </h2>
        {empty && <p className="text-sm text-muted-foreground">{t("factory.none")}</p>}
        {factory.products.length > 0 && (
          <div className="space-y-1">
            <h3 className="text-xs font-medium uppercase text-muted-foreground">{t("factory.products")}</h3>
            <div className="flex flex-wrap gap-2">
              {factory.products.map((p) => (
                <Badge key={p.id} variant="outline">
                  {p.name}
                </Badge>
              ))}
            </div>
          </div>
        )}
        {factory.projects.length > 0 && (
          <div className="space-y-1">
            <h3 className="text-xs font-medium uppercase text-muted-foreground">{t("factory.projects")}</h3>
            <ul className="divide-y">
              {factory.projects.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <Link to={`/projects/${p.id}`} className="font-medium underline">
                    {p.name}
                  </Link>
                  <Badge variant="outline">{p.status}</Badge>
                  {p.darckware_origin_type && (
                    <span className="text-xs text-muted-foreground">{t(`factory.origin.${p.darckware_origin_type}`)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        {factory.unlinked_products.length > 0 && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-1">
              <label htmlFor="link-product" className="text-sm">
                {t("factory.link")}
              </label>
              <Select
                id="link-product"
                className="max-md:text-base"
                value={vm.linkProductId}
                onChange={(e) => vm.setLinkProductId(e.target.value)}
              >
                <option value="">{t("factory.linkPick")}</option>
                {factory.unlinked_products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </div>
            <Button variant="outline" onClick={() => void vm.linkProduct()} disabled={!vm.linkProductId || vm.linking}>
              {vm.linking && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("factory.linkConfirm")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function OpenWorkSection({ vm, clientId }: { vm: ClientAccountViewModel; clientId: string }) {
  const { t } = useTranslation("clientOps");
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold">{t("accounts.openWork")}</h2>
          {vm.openWork.length > 0 && <Badge variant="warning">{vm.openWork.length}</Badge>}
        </div>
        {vm.openWorkLoading && <Loader2 className="h-5 w-5 animate-spin" />}
        {!vm.openWorkLoading && vm.openWork.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("accounts.noOpenWork")}</p>
        )}
        <ul className="divide-y">
          {vm.openWork.map((item) => (
            <li key={`${item.kind}:${item.id}`} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 space-y-1">
                <div className="break-words font-medium">{item.title}</div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  <Badge variant={stageVariant(item.stage)}>{t(`stage.${item.stage}`)}</Badge>
                  <span>{t(`kind.${item.kind}`)}</span>
                  <span>· {t(`tipo.${item.tipo}`)}</span>
                  {item.priority && <span>· {t(`priority.${item.priority}`, item.priority)}</span>}
                  {item.created_at && <span>· {new Date(item.created_at).toLocaleDateString()}</span>}
                </div>
              </div>
              <Link
                to={clientDemandsLink(clientId, { kind: item.kind, id: item.id })}
                className={buttonVariants({ size: "sm", className: "shrink-0" })}
              >
                {t("accounts.resolve")}
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function EmailsSection({ title, empty, emails }: { title: string; empty: string; emails: OutboundEmail[] }) {
  const { t } = useTranslation("clientOps");
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <h2 className="font-semibold">{title}</h2>
        {emails.length === 0 && <p className="text-sm text-muted-foreground">{empty}</p>}
        <ul className="divide-y">
          {emails.map((e) => (
            <li key={e.id} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="break-words text-sm font-medium">{e.subject}</div>
                <div className="text-xs text-muted-foreground">
                  {t(`emails.kind.${e.kind}`, e.kind)} · v{e.version}
                  {e.sent_at ? ` · ${new Date(e.sent_at).toLocaleString()}` : e.created_at ? ` · ${new Date(e.created_at).toLocaleString()}` : ""}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant={emailStatusVariant(e.status)}>{t(`emails.status.${e.status}`, e.status)}</Badge>
                <Link to={`/client-emails?id=${e.id}`} className="text-xs underline">
                  {t("accounts.openEmail")}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
