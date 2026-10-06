import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRightLeft,
  Briefcase,
  ChevronRight,
  CirclePlus,
  Clock,
  FolderKanban,
  Loader2,
  Mail,
  MessageSquare,
  Plus,
  User,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useClientOpsStatus,
  useClientOpsText,
  useDarckwareClients,
  WORK_ITEM_STAGES,
  type WorkItemKind,
  type WorkItemStage,
  type WorkItemDetail,
  type WorkItemTipo,
} from "@/hooks/useClientOps";
import { billableHours, buildTimeline, STAGE_FLOW } from "@/hooks/clientDemandTimeline";
import {
  ACTIONS_BY_STAGE,
  ACTION_EMAIL,
  parseDemandsSearch,
  useClientDemandsViewModel,
  type ClientDemandsViewModel,
} from "@/hooks/useClientDemandsViewModel";
import { cn } from "@/lib/utils";
import { NewWorkItemDialog } from "./NewWorkItemDialog";
import { ClientOpsStatusBanner, stageVariant } from "./shared";

export default function ClientDemandsPage() {
  const { t } = useTranslation("clientOps");
  const [search] = useSearchParams();
  const [initial] = useState(() => parseDemandsSearch(search));
  const vm = useClientDemandsViewModel(initial);
  const integration = useClientOpsStatus();
  const clients = useDarckwareClients();
  const [creating, setCreating] = useState(false);
  const pendingEmails = integration.data?.pending_emails ?? 0;

  return (
    <div className="flex flex-col gap-4 md:h-full md:min-h-0">
      <PageHeader
        title={t("demands.title")}
        description={t("demands.description")}
        icon={<Briefcase className="h-6 w-6" />}
        actions={
          <>
            <Link to="/client-emails" className={buttonVariants({ variant: "outline" })}>
              <Mail className="mr-2 h-4 w-4" />
              {t("demands.emailsPending")}
              {pendingEmails > 0 && <Badge variant="warning" className="ml-2">{pendingEmails}</Badge>}
            </Link>
            <Button onClick={() => setCreating(true)} disabled={!integration.data?.configured}>
              <Plus className="mr-2 h-4 w-4" /> {t("demands.new")}
            </Button>
          </>
        }
      />
      <ClientOpsStatusBanner status={integration.data} />

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Select
          aria-label={t("demands.filters.client")}
          className="max-md:text-base"
          value={vm.filters.client_account_id ?? ""}
          onChange={(e) => vm.setFilter("client_account_id", e.target.value)}
        >
          <option value="">{t("demands.filters.allClients")}</option>
          {(clients.data?.items ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.company_name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("demands.filters.kind")}
          className="max-md:text-base"
          value={vm.filters.kind ?? ""}
          onChange={(e) => vm.setFilter("kind", e.target.value as WorkItemKind)}
        >
          <option value="">{t("demands.filters.allKinds")}</option>
          <option value="ticket">{t("kind.ticket")}</option>
          <option value="demand">{t("kind.demand")}</option>
        </Select>
        <Select
          aria-label={t("demands.filters.tipo")}
          className="max-md:text-base"
          value={vm.filters.tipo ?? ""}
          onChange={(e) => vm.setFilter("tipo", e.target.value as WorkItemTipo)}
        >
          <option value="">{t("demands.filters.allTipos")}</option>
          <option value="desenvolvimento">{t("tipo.desenvolvimento")}</option>
          <option value="servico">{t("tipo.servico")}</option>
        </Select>
        <Select
          aria-label={t("demands.filters.stage")}
          className="max-md:text-base"
          value={vm.filters.stage ?? ""}
          onChange={(e) => vm.setFilter("stage", e.target.value as WorkItemStage | "open")}
        >
          <option value="open">{t("stage.open")}</option>
          <option value="">{t("stage.all")}</option>
          {WORK_ITEM_STAGES.map((s) => (
            <option key={s} value={s}>
              {t(`stage.${s}`)}
              {vm.byStage ? ` (${vm.byStage[s] ?? 0})` : ""}
            </option>
          ))}
        </Select>
      </div>

      <div className="grid grid-cols-1 gap-4 md:min-h-0 md:flex-1 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card className={cn("md:min-h-0 md:overflow-auto", vm.selected && "max-md:hidden")}>
          <CardContent className="p-0">
            {vm.status === "loading" && (
              <div className="flex justify-center p-6">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            )}
            {vm.loadError && <p className="break-words p-4 text-sm text-destructive">{vm.loadError}</p>}
            {!vm.loadError && vm.status !== "loading" && vm.items.length === 0 && (
              <p className="p-6 text-sm text-muted-foreground">{t("demands.empty")}</p>
            )}
            <ul className="divide-y">
              {vm.items.map((item) => (
                <li key={`${item.kind}:${item.id}`}>
                  <button
                    type="button"
                    onClick={() => vm.select(item)}
                    className={cn(
                      "w-full space-y-1 px-4 py-3 text-left hover:bg-muted/50",
                      vm.selected?.id === item.id && "bg-muted",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{item.title}</span>
                      <Badge variant={stageVariant(item.stage)} className="shrink-0">
                        {t(`stage.${item.stage}`)}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      <span>{item.company_name ?? "—"}</span>
                      <span>{t(`kind.${item.kind}`)}</span>
                      <span>{t(`tipo.${item.tipo}`)}</span>
                      {item.priority && <span>{t(`priority.${item.priority}`, item.priority)}</span>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className={cn("md:min-h-0 md:overflow-auto", !vm.selected && "max-md:hidden")}>
          <CardContent className="space-y-4 p-4">
            <WorkItemDetailPane vm={vm} />
          </CardContent>
        </Card>
      </div>

      {vm.draft && <ActionDialog vm={vm} />}
      {vm.projectDraft && <CreateProjectDialog vm={vm} />}
      {vm.timeDraft && <LogTimeDialog vm={vm} />}
      <NewWorkItemDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(item) => {
          setCreating(false);
          vm.select(item);
        }}
      />
    </div>
  );
}

function WorkItemDetailPane({ vm }: { vm: ClientDemandsViewModel }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const detail = vm.detail;
  if (!vm.selected) return <p className="text-sm text-muted-foreground">{t("demands.selectHint")}</p>;
  const actions = detail ? (ACTIONS_BY_STAGE[detail.stage] ?? []) : [];
  const canLogTime = Boolean(detail?.client_account_id) && detail?.stage !== "fechado";
  // A project only makes sense for development work; a service demand never shows it.
  const canCreateProject =
    detail?.tipo === "desenvolvimento" && !detail.project && !vm.projectBlockedReason && detail.stage !== "fechado";
  return (
    <>
      <button
        type="button"
        className="flex items-center gap-1 text-sm text-muted-foreground md:hidden"
        onClick={() => vm.select(undefined)}
      >
        <ArrowLeft className="h-4 w-4" /> {t("demands.back")}
      </button>
      {vm.detailLoading && <Loader2 className="h-5 w-5 animate-spin" />}
      {vm.detailError && <p className="break-words text-sm text-destructive">{vm.detailError}</p>}
      {vm.errorMessage && !vm.draft && !vm.projectDraft && !vm.timeDraft && (
        <div className="flex items-start justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <span className="break-words">{vm.errorMessage}</span>
          <button type="button" onClick={vm.dismissError} aria-label={t("common.dismiss")}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {vm.lastQueuedEmail && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">
          <span>{t("demands.queued")}</span>
          <Link to="/client-emails" className="underline">
            {t("demands.openApproval")}
          </Link>
        </div>
      )}
      {detail && (
        <>
          <h2 className="break-words text-lg font-semibold">{detail.title}</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Field label={t("demands.fields.situation")}>
              <Badge variant={stageVariant(detail.stage)}>{t(`stage.${detail.stage}`)}</Badge>
            </Field>
            <Field label={t("demands.fields.tipo")}>{t(`tipo.${detail.tipo}`)}</Field>
            <Field label={t("demands.fields.priority")}>
              {detail.priority ? (
                <span className={cn(detail.priority === "urgente" && "font-semibold text-destructive")}>
                  {t(`priority.${detail.priority}`, detail.priority)}
                </span>
              ) : (
                "—"
              )}
            </Field>
            <Field label={t("demands.fields.origin")}>
              {t(`kind.${detail.kind}`)}
              {detail.source && (
                <span className="text-muted-foreground"> · {t(`source.${detail.source}`, { defaultValue: detail.source })}</span>
              )}
            </Field>
          </dl>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">{t("demands.fields.client")}</dt>
            <dd>{detail.company_name ?? "—"}</dd>
            <dt className="text-muted-foreground">{t("demands.fields.requester")}</dt>
            <dd className="break-all">
              {[detail.requester_name, detail.requester_email].filter(Boolean).join(" · ") || "—"}
            </dd>
            {detail.billable_hours != null && (
              <>
                <dt className="text-muted-foreground">{t("demands.fields.hours")}</dt>
                <dd>{fmt.hours(detail.billable_hours)}</dd>
              </>
            )}
          </dl>
          {detail.description && <p className="whitespace-pre-wrap break-words text-sm">{detail.description}</p>}

          <section className="space-y-3 rounded-md border p-3">
            <h3 className="text-sm font-semibold">{t("demands.flow.title")}</h3>
            <StageProgress stage={detail.stage} />
            {actions.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("demands.flow.change")}</p>
                <ul className="space-y-2">
                  {actions.map((action) => (
                    <li key={action} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                      <Button
                        size="sm"
                        variant={action === "resolve" ? "default" : "outline"}
                        className="shrink-0 sm:w-44 max-md:h-auto max-md:whitespace-normal"
                        onClick={() => vm.openAction(action)}
                      >
                        {t(`demands.actions.${action}`)}
                      </Button>
                      <span className="text-xs text-muted-foreground">{t(`demands.actionHelp.${action}`)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {(canLogTime || canCreateProject || detail.project || vm.projectBlockedReason) && (
            <section className="space-y-2 rounded-md border p-3">
              <h3 className="text-sm font-semibold">{t("demands.flow.work")}</h3>
              <ul className="space-y-2">
                {canLogTime && (
                  <li className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                    <Button size="sm" variant="outline" className="shrink-0 sm:w-44 max-md:h-auto max-md:whitespace-normal" onClick={vm.openLogTime}>
                      <Clock className="mr-2 h-4 w-4" /> {t("time.log")}
                    </Button>
                    <span className="text-xs text-muted-foreground">{t("demands.workHelp.log")}</span>
                  </li>
                )}
                {canCreateProject && (
                  <li className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                    <Button size="sm" variant="outline" className="shrink-0 sm:w-44 max-md:h-auto max-md:whitespace-normal" onClick={vm.openCreateProject}>
                      <FolderKanban className="mr-2 h-4 w-4" /> {t("project.create")}
                    </Button>
                    <span className="text-xs text-muted-foreground">{t("demands.workHelp.project")}</span>
                  </li>
                )}
              </ul>
              {detail.project ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <FolderKanban className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">{t("project.linked")}:</span>
                  <Link to={`/projects/${detail.project.id}`} className="font-medium underline">
                    {detail.project.name}
                  </Link>
                </div>
              ) : (
                detail.tipo === "desenvolvimento" &&
                vm.projectBlockedReason === "noClient" && <p className="text-xs text-muted-foreground">{t("project.noClient")}</p>
              )}
            </section>
          )}

          <WorkItemTimeline detail={detail} />
        </>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}

/** Nova → Em andamento → Aguardando cliente → Resolvida → Fechada, current stage marked. */
function StageProgress({ stage }: { stage: WorkItemStage }) {
  const { t } = useTranslation("clientOps");
  const current = STAGE_FLOW.indexOf(stage);
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs">
      {STAGE_FLOW.map((s, i) => (
        <li key={s} className="flex items-center gap-1">
          <span
            aria-current={i === current ? "step" : undefined}
            className={cn(
              "rounded-full border px-2 py-0.5",
              i === current && "border-primary bg-primary font-semibold text-primary-foreground",
              i < current && "border-primary/40 text-foreground",
              i > current && "text-muted-foreground",
            )}
          >
            {t(`stage.${s}`)}
          </span>
          {i < STAGE_FLOW.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function WorkItemTimeline({ detail }: { detail: WorkItemDetail }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const entries = buildTimeline(detail);
  const by = (who: string) => (who ? ` · ${t("demands.event.by", { who })}` : "");
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{t("demands.history")}</h3>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("demands.noTimeline")}</p>
      ) : (
        <ol className="space-y-3 border-l pl-4">
          {entries.map((e, i) => {
            let icon: ReactNode = <MessageSquare className="h-3.5 w-3.5" />;
            let title = "";
            let body: string | undefined;
            let actor = "";
            switch (e.kind) {
              case "opened":
                icon = <CirclePlus className="h-3.5 w-3.5" />;
                title = e.source
                  ? t("demands.event.openedVia", { source: t(`source.${e.source}`, { defaultValue: e.source }) })
                  : t("demands.event.opened");
                break;
              case "status":
                icon = <ArrowRightLeft className="h-3.5 w-3.5" />;
                title = e.from
                  ? t("demands.event.status", { from: t(`stage.${e.from}`), to: t(`stage.${e.to}`) })
                  : t("demands.event.statusTo", { to: t(`stage.${e.to}`) });
                body = e.note;
                actor = e.actor;
                break;
              case "hours":
                icon = <Clock className="h-3.5 w-3.5" />;
                title = t("demands.event.hours", { hours: fmt.hours(e.hours) });
                body = [e.description, e.start && e.end ? t("demands.event.period", { start: fmt.dateTime(e.start), end: fmt.dateTime(e.end) }) : ""]
                  .filter(Boolean)
                  .join("\n");
                actor = e.actor;
                break;
              case "email":
                icon = <Mail className="h-3.5 w-3.5" />;
                title = t(`demands.event.email.${e.event}`);
                body = e.subject;
                break;
              case "client":
                icon = <User className="h-3.5 w-3.5" />;
                title = t("demands.event.client");
                body = e.text;
                actor = e.actor;
                break;
              case "note":
                title = t("demands.event.note");
                body = e.text;
                actor = e.actor;
                break;
            }
            return (
              <li key={`${e.kind}-${e.at}-${i}`} className="relative text-sm">
                <span className="absolute -left-[1.6rem] top-0.5 flex h-5 w-5 items-center justify-center rounded-full border bg-background text-muted-foreground">
                  {icon}
                </span>
                <div className="font-medium">{title}</div>
                <div className="text-xs text-muted-foreground">
                  {fmt.dateTime(e.at)}
                  {by(actor)}
                </div>
                {body && <p className="mt-0.5 whitespace-pre-wrap break-words text-muted-foreground">{body}</p>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function ActionDialog({ vm }: { vm: ClientDemandsViewModel }) {
  const { t } = useTranslation("clientOps");
  const draft = vm.draft!;
  const submitting = vm.status === "submitting";
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={vm.cancelAction} aria-hidden />
      <div className="relative my-auto w-full max-w-lg space-y-4 rounded-lg border bg-background p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{t(`demands.actions.${draft.action}`)}</h2>
        <div className="space-y-1">
          <Label htmlFor="action-text">{t(`demands.dialog.text.${draft.action}`)}</Label>
          <Textarea
            id="action-text"
            rows={3}
            className="max-md:text-base"
            value={draft.text}
            onChange={(e) => vm.updateDraft({ text: e.target.value })}
          />
        </div>
        {draft.action === "resolve" && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="action-hours">{t("time.spent")}</Label>
              <Input
                id="action-hours"
                inputMode="decimal"
                placeholder="1,5"
                className="max-md:text-base"
                value={draft.hours}
                onChange={(e) => vm.updateDraft({ hours: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                {vm.hoursRequired ? t("time.spentHelp") : t("time.spentNoClient")}
              </p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="action-service">{t("time.serviceType")}</Label>
              <Select
                id="action-service"
                className="max-md:text-base"
                value={draft.serviceType}
                onChange={(e) => vm.updateDraft({ serviceType: e.target.value as "remoto" | "presencial" })}
              >
                <option value="remoto">{t("time.remoto")}</option>
                <option value="presencial">{t("time.presencial")}</option>
              </Select>
            </div>
          </div>
        )}
        {ACTION_EMAIL[draft.action] && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.withEmail}
              onChange={(e) => vm.updateDraft({ withEmail: e.target.checked })}
            />
            {t("demands.dialog.withEmail")}
          </label>
        )}
        {draft.withEmail && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="action-to">{t("demands.dialog.to")}</Label>
              <Input
                id="action-to"
                className="max-md:text-base"
                value={draft.to_email}
                onChange={(e) => vm.updateDraft({ to_email: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="action-subject">{t("demands.dialog.subject")}</Label>
              <Input
                id="action-subject"
                className="max-md:text-base"
                value={draft.subject}
                onChange={(e) => vm.updateDraft({ subject: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="action-body">{t("demands.dialog.body")}</Label>
              <Textarea
                id="action-body"
                rows={8}
                className="max-md:text-base"
                value={draft.body_text}
                onChange={(e) => vm.updateDraft({ body_text: e.target.value })}
              />
            </div>
          </div>
        )}
        {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={vm.cancelAction} disabled={submitting}>
            {t("demands.dialog.cancel")}
          </Button>
          <Button onClick={() => void vm.submitAction()} disabled={!vm.canSubmitAction}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("demands.dialog.confirm")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function CreateProjectDialog({ vm }: { vm: ClientDemandsViewModel }) {
  const { t } = useTranslation("clientOps");
  const draft = vm.projectDraft!;
  const submitting = vm.status === "submitting";
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={vm.cancelCreateProject} aria-hidden />
      <div role="dialog" aria-modal="true" className="relative my-auto w-full max-w-lg space-y-4 rounded-lg border bg-background p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{t("project.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("project.explain")}</p>
        <div className="flex flex-wrap gap-4 text-sm">
          {(["existing", "new"] as const).map((choice) => (
            <label key={choice} className="flex items-center gap-2">
              <input
                type="radio"
                name="product-choice"
                checked={draft.productChoice === choice}
                onChange={() => vm.updateProjectDraft({ productChoice: choice })}
              />
              {t(`project.${choice}`)}
            </label>
          ))}
        </div>
        {draft.productChoice === "existing" ? (
          <div className="space-y-1">
            <Label htmlFor="pj-product">{t("project.product")}</Label>
            <Select
              id="pj-product"
              className="max-md:text-base"
              value={draft.productId}
              onChange={(e) => vm.updateProjectDraft({ productId: e.target.value })}
            >
              <option value="">{t("project.chooseProduct")}</option>
              {vm.projectProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.darckware_client_name ? ` · ${p.darckware_client_name}` : ""}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">{t("project.unlinkedHint")}</p>
          </div>
        ) : (
          <div className="space-y-1">
            <Label htmlFor="pj-new">{t("project.productName")}</Label>
            <Input
              id="pj-new"
              className="max-md:text-base"
              value={draft.newProductName}
              onChange={(e) => vm.updateProjectDraft({ newProductName: e.target.value })}
            />
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="pj-name">{t("project.projectName")}</Label>
          <Input
            id="pj-name"
            className="max-md:text-base"
            value={draft.projectName}
            onChange={(e) => vm.updateProjectDraft({ projectName: e.target.value })}
          />
        </div>
        {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={vm.cancelCreateProject} disabled={submitting}>
            {t("project.cancel")}
          </Button>
          <Button onClick={() => void vm.submitCreateProject()} disabled={!vm.canSubmitProject}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("project.confirm")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function LogTimeDialog({ vm }: { vm: ClientDemandsViewModel }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const d = vm.timeDraft!;
  const submitting = vm.status === "submitting";
  const minutes = vm.timeDraftMinutes;
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
      <div className="fixed inset-0 bg-black/60" onClick={vm.cancelLogTime} aria-hidden />
      <div role="dialog" aria-modal="true" className="relative my-auto w-full max-w-lg space-y-4 rounded-lg border bg-background p-5 shadow-xl">
        <h2 className="text-lg font-semibold">{t("time.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("time.rounding")}</p>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("time.startAt")}</legend>
          <div className="grid grid-cols-2 gap-3">
            <Input id="tm-start-day" type="date" aria-label={`${t("time.startAt")} · ${t("time.day")}`} className="max-md:text-base" value={d.startDay} onChange={(e) => vm.updateTimeDraft({ startDay: e.target.value })} />
            <Input id="tm-start" type="time" aria-label={`${t("time.startAt")} · ${t("time.hour")}`} className="max-md:text-base" value={d.start} onChange={(e) => vm.updateTimeDraft({ start: e.target.value })} />
          </div>
        </fieldset>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("time.endAt")}</legend>
          <div className="grid grid-cols-2 gap-3">
            <Input id="tm-end-day" type="date" aria-label={`${t("time.endAt")} · ${t("time.day")}`} className="max-md:text-base" value={d.endDay} onChange={(e) => vm.updateTimeDraft({ endDay: e.target.value })} />
            <Input id="tm-end" type="time" aria-label={`${t("time.endAt")} · ${t("time.hour")}`} className="max-md:text-base" value={d.end} onChange={(e) => vm.updateTimeDraft({ end: e.target.value })} />
          </div>
        </fieldset>
        {vm.timeDraftError ? (
          <p className="text-xs text-destructive">{t(`time.${vm.timeDraftError}`)}</p>
        ) : (
          minutes > 0 && (
            <p className="rounded-md bg-muted px-3 py-2 text-sm">
              {t("time.total", {
                duration: t("time.duration", { h: Math.floor(minutes / 60), m: minutes % 60 }),
                billable: fmt.hours(billableHours(minutes)),
              })}
            </p>
          )
        )}
        <div className="space-y-1">
          <Label htmlFor="tm-type">{t("time.serviceType")}</Label>
          <Select
            id="tm-type"
            className="max-md:text-base"
            value={d.serviceType}
            onChange={(e) => vm.updateTimeDraft({ serviceType: e.target.value as "remoto" | "presencial" })}
          >
            <option value="remoto">{t("time.remoto")}</option>
            <option value="presencial">{t("time.presencial")}</option>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="tm-desc">{t("time.description")}</Label>
          <Textarea id="tm-desc" rows={3} className="max-md:text-base" value={d.description} onChange={(e) => vm.updateTimeDraft({ description: e.target.value })} />
        </div>
        {vm.errorMessage && <p className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={vm.cancelLogTime} disabled={submitting}>
            {t("time.cancel")}
          </Button>
          <Button onClick={() => void vm.submitLogTime()} disabled={!vm.canSubmitTime}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("time.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}
