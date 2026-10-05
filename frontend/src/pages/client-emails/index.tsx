import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, Loader2, Mail, Pencil, X } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ClientOpsStatusBanner, emailStatusVariant } from "@/pages/client-demands/shared";
import { useClientOpsStatus } from "@/hooks/useClientOps";
import {
  useClientEmailApprovalViewModel,
  type EmailListFilter,
} from "@/hooks/useClientEmailApprovalViewModel";
import { cn } from "@/lib/utils";

const FILTERS: EmailListFilter[] = ["pending", "aprovado", "enviado", "all"];

export default function ClientEmailsPage() {
  const { t } = useTranslation("clientOps");
  const [search] = useSearchParams();
  const [initialId] = useState(() => search.get("id") || undefined);
  const vm = useClientEmailApprovalViewModel(initialId);
  const integration = useClientOpsStatus();
  const selected = vm.selected;

  return (
    <div className="flex flex-col gap-4 md:h-full md:min-h-0">
      <PageHeader title={t("emails.title")} description={t("emails.description")} icon={<Mail className="h-6 w-6" />} />
      <ClientOpsStatusBanner status={integration.data} />

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Button key={f} size="sm" variant={vm.filter === f ? "default" : "outline"} onClick={() => vm.setFilter(f)}>
            {t(`emails.filter.${f}`)}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 md:min-h-0 md:flex-1 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card className={cn("md:min-h-0 md:overflow-auto", vm.selectedId && "max-md:hidden")}>
          <CardContent className="p-0">
            {vm.status === "loading" && (
              <div className="flex justify-center p-6">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            )}
            {vm.loadError && <p className="p-4 text-sm text-destructive">{vm.loadError}</p>}
            {!vm.loadError && vm.status !== "loading" && vm.emails.length === 0 && (
              <p className="p-6 text-sm text-muted-foreground">{t("emails.empty")}</p>
            )}
            <ul className="divide-y">
              {vm.emails.map((email) => (
                <li key={email.id}>
                  <button
                    type="button"
                    onClick={() => vm.select(email.id)}
                    className={cn(
                      "w-full space-y-1 px-4 py-3 text-left hover:bg-muted/50",
                      vm.selectedId === email.id && "bg-muted",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{email.subject}</span>
                      <Badge variant={emailStatusVariant(email.status)} className="shrink-0">
                        {t(`emails.status.${email.status}`, email.status)}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      <span className="break-all">{email.to_email}</span>
                      <span>{t(`emails.kind.${email.kind}`, email.kind)}</span>
                      <span>v{email.version}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className={cn("md:min-h-0 md:overflow-auto", !vm.selectedId && "max-md:hidden")}>
          <CardContent className="space-y-4 p-4">
            {vm.selectedId && (
              <button
                type="button"
                className="flex items-center gap-1 text-sm text-muted-foreground md:hidden"
                onClick={() => vm.select(undefined)}
              >
                <ArrowLeft className="h-4 w-4" /> {t("emails.back")}
              </button>
            )}
            {!vm.selectedId && <p className="text-sm text-muted-foreground">{t("emails.selectHint")}</p>}
            {vm.detailLoading && <Loader2 className="h-5 w-5 animate-spin" />}
            {vm.errorMessage && (
              <div className="flex items-start justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <span>{vm.errorMessage}</span>
                <button type="button" onClick={vm.dismiss} aria-label={t("common.dismiss")}>
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {selected && (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={emailStatusVariant(selected.status)}>
                    {t(`emails.status.${selected.status}`, selected.status)}
                  </Badge>
                  <Badge variant="outline">{t(`emails.kind.${selected.kind}`, selected.kind)}</Badge>
                  <Badge variant="outline">{t("emails.version", { version: selected.version })}</Badge>
                </div>

                <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                  <dt className="text-muted-foreground">{t("emails.from")}</dt>
                  <dd className="break-all">{selected.sender ? `${selected.sender.name} <${selected.sender.email}>` : "—"}</dd>
                  <dt className="text-muted-foreground">{t("emails.to")}</dt>
                  <dd className="break-all">{selected.to_email}</dd>
                  <dt className="text-muted-foreground">{t("emails.createdBy")}</dt>
                  <dd>{selected.created_by}</dd>
                  {selected.approved_by && (
                    <>
                      <dt className="text-muted-foreground">{t("emails.approvedBy")}</dt>
                      <dd>{selected.approved_by}</dd>
                    </>
                  )}
                  {selected.error && (
                    <>
                      <dt className="text-muted-foreground">{t("emails.error")}</dt>
                      <dd className="break-words text-destructive">{selected.error}</dd>
                    </>
                  )}
                  {selected.rejected_reason && (
                    <>
                      <dt className="text-muted-foreground">{t("emails.rejected")}</dt>
                      <dd className="break-words">{selected.rejected_reason}</dd>
                    </>
                  )}
                </dl>

                {vm.editing ? (
                  <div className="space-y-3">
                    <p className="text-sm text-amber-600">{t("emails.editWarning")}</p>
                    <div className="space-y-1">
                      <Label htmlFor="email-to">{t("emails.to")}</Label>
                      <Input
                        id="email-to"
                        className="max-md:text-base"
                        value={vm.draft.to_email}
                        onChange={(e) => vm.setDraft({ to_email: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="email-subject">{t("demands.dialog.subject")}</Label>
                      <Input
                        id="email-subject"
                        className="max-md:text-base"
                        value={vm.draft.subject}
                        onChange={(e) => vm.setDraft({ subject: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="email-body">{t("demands.dialog.body")}</Label>
                      <Textarea
                        id="email-body"
                        rows={12}
                        className="max-md:text-base"
                        value={vm.draft.body_text}
                        onChange={(e) => vm.setDraft({ body_text: e.target.value })}
                      />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={() => void vm.saveEdit()} disabled={vm.status === "submitting"}>
                        {vm.status === "submitting" && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {t("emails.save")}
                      </Button>
                      <Button variant="outline" onClick={vm.cancelEdit}>
                        {t("emails.cancelEdit")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-2">
                      {vm.canApprove && (
                        <Button onClick={vm.requestApprove} disabled={vm.status === "submitting"}>
                          <Check className="mr-2 h-4 w-4" /> {t("emails.approve")}
                        </Button>
                      )}
                      {vm.canEdit && (
                        <Button variant="outline" onClick={vm.startEdit}>
                          <Pencil className="mr-2 h-4 w-4" /> {t("emails.edit")}
                        </Button>
                      )}
                      {vm.canEdit && (
                        <Button variant="outline" onClick={vm.requestReject}>
                          {t("emails.reject")}
                        </Button>
                      )}
                      {vm.canEdit && (
                        <Button variant="ghost" className="text-destructive" onClick={vm.requestCancel}>
                          {t("emails.cancelEmail")}
                        </Button>
                      )}
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-medium">{t("emails.preview")}</p>
                      {selected.preview_html ? (
                        <iframe
                          title={t("emails.preview")}
                          sandbox=""
                          srcDoc={selected.preview_html}
                          className="h-[520px] w-full rounded-md border bg-[#0A0D14]"
                        />
                      ) : (
                        <pre className="whitespace-pre-wrap break-words rounded-md border p-3 text-sm">
                          {selected.body_text}
                        </pre>
                      )}
                    </div>
                  </>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={vm.dialog === "approve"}
        loading={vm.status === "submitting"}
        variant="default"
        icon="warning"
        title={t("emails.confirmApproveTitle")}
        description={t("emails.confirmApproveBody", { version: selected?.version, to: selected?.to_email })}
        confirmLabel={t("emails.approve")}
        onConfirm={() => void vm.confirmApprove()}
        onCancel={vm.dismiss}
      />
      <ConfirmDialog
        open={vm.dialog === "reject"}
        loading={vm.status === "submitting"}
        title={t("emails.confirmRejectTitle")}
        confirmLabel={t("emails.reject")}
        confirmDisabled={!vm.rejectReason.trim()}
        onConfirm={() => void vm.confirmReject()}
        onCancel={vm.dismiss}
      >
        <div className="space-y-1">
          <Label htmlFor="reject-reason">{t("emails.rejectReason")}</Label>
          <Textarea
            id="reject-reason"
            rows={3}
            className="max-md:text-base"
            value={vm.rejectReason}
            onChange={(e) => vm.setRejectReason(e.target.value)}
          />
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={vm.dialog === "cancel"}
        loading={vm.status === "submitting"}
        title={t("emails.confirmCancelTitle")}
        description={t("emails.confirmCancelBody")}
        confirmLabel={t("emails.cancelEmail")}
        onConfirm={() => void vm.confirmCancel()}
        onCancel={vm.dismiss}
      />
    </div>
  );
}
