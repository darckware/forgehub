/**
 * Tailnet policy (ACL) on the Remote Access page (2026-10-16, Marcelo: "seria
 * bom gravar essa regra do acl na tela do acesso remoto"). Records pasted
 * copies of the Tailscale policy and says whether ForgeHub's server can reach
 * each client tag over SSH -- the rule whose absence made every station read
 * "SSH port unreachable". Tailscale's console stays where it is applied.
 */
import { useTranslation } from "react-i18next";
import { Check, CheckCircle2, Copy, ExternalLink, FileCode2, Loader2, Pencil, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useTailnetPolicyViewModel } from "@/hooks/useTailnetPolicyViewModel";
import { cn } from "@/lib/utils";

const ADMIN_CONSOLE = "https://login.tailscale.com/admin/acls";

export function TailnetPolicyCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useTailnetPolicyViewModel();
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const current = vm.state?.current ?? null;
  const analysis = current?.analysis ?? null;

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("policy.title")}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{t("policy.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={ADMIN_CONSOLE} target="_blank" rel="noreferrer" className={cn(buttonVariants({ size: "sm", variant: "outline" }), "gap-1.5")}>
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /> {t("policy.openConsole")}
          </a>
          {vm.status !== "editing" && vm.status !== "saving" && (
            <Button type="button" size="sm" onClick={vm.startEditing} className="cursor-pointer gap-1.5">
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> {t(current ? "policy.recordNew" : "policy.record")}
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {vm.status === "loading" ? (
          <p className="text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : vm.status === "error" ? (
          <p className="text-sm text-destructive" role="alert">{t("policy.loadFailed")}</p>
        ) : vm.status === "editing" || vm.status === "saving" ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">{t("policy.pasteHelp")}</p>
            <Textarea
              aria-label={t("policy.content")}
              value={vm.draft}
              onChange={(e) => vm.setDraft(e.target.value)}
              className="min-h-[280px] font-mono text-xs max-md:text-base"
              spellCheck={false}
            />
            <Input
              aria-label={t("policy.note")}
              value={vm.note}
              onChange={(e) => vm.setNote(e.target.value)}
              placeholder={t("policy.notePlaceholder")}
              className="max-md:text-base"
            />
            {vm.saveError && <p role="alert" className="text-xs text-destructive">{vm.saveError}</p>}
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={vm.cancelEditing} disabled={vm.status === "saving"} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={vm.save} disabled={vm.status === "saving" || vm.draft.trim().length < 2} className="cursor-pointer gap-1.5">
                {vm.status === "saving" && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                {t("policy.save")}
              </Button>
            </div>
          </div>
        ) : !current ? (
          <p className="text-sm text-muted-foreground">{t("policy.empty")}</p>
        ) : (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted-foreground">
                {t("policy.recordedBy", { who: current.saved_by, when: fmt.format(new Date(current.created_at)) })}
                {current.note && ` · ${current.note}`}
              </p>
              {(vm.state?.versions.length ?? 0) > 1 && (
                <label className="sm:w-64">
                  <span className="sr-only">{t("policy.versions")}</span>
                  <Select
                    value={vm.selectedVersionId ?? ""}
                    onChange={(e) => vm.selectVersion(e.target.value || null)}
                    className="max-md:text-base"
                  >
                    <option value="">{t("policy.latest")}</option>
                    {vm.state?.versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {fmt.format(new Date(v.created_at))} · {v.saved_by}{v.note ? ` · ${v.note}` : ""}
                      </option>
                    ))}
                  </Select>
                </label>
              )}
            </div>

            {current.parse_error ? (
              <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">{current.parse_error}</p>
            ) : analysis && (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {analysis.client_tags.map((tag) => {
                    const ok = analysis.tags_with_ssh.includes(tag);
                    return (
                      <Badge key={tag} variant={ok ? "success" : "destructive"} className="gap-1 font-mono">
                        {ok ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : <TriangleAlert className="h-3 w-3" aria-hidden="true" />}
                        {tag}
                      </Badge>
                    );
                  })}
                </div>
                {analysis.missing_ssh.length === 0 ? (
                  <p className="flex items-center gap-2 text-sm text-emerald-600">
                    <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> {t("policy.allGood", { server: analysis.server_tag })}
                  </p>
                ) : (
                  <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
                    <p className="text-sm">{t("policy.missing", { server: analysis.server_tag, count: analysis.missing_ssh.length })}</p>
                    {analysis.snippet && (
                      <div className="relative">
                        <pre className="overflow-auto whitespace-pre rounded-md border border-border bg-background p-3 font-mono text-xs">{analysis.snippet}</pre>
                        <Button type="button" size="sm" variant="outline" onClick={vm.copySnippet} className="absolute right-2 top-2 cursor-pointer gap-1.5">
                          {vm.copiedSnippet ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                          {t(vm.copiedSnippet ? "prepare.copied" : "prepare.copy")}
                        </Button>
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground">{t(analysis.style === "acls" ? "policy.whereAcls" : "policy.whereGrants")}</p>
                  </div>
                )}
                {analysis.warnings.map((w) => <p key={w} className="text-xs text-amber-600">{w}</p>)}
              </div>
            )}

            <button type="button" onClick={vm.toggleContent} className="cursor-pointer text-xs text-primary hover:underline">
              {t(vm.showContent ? "policy.hideContent" : "policy.showContent")}
            </button>
            {vm.showContent && (
              <pre className="max-h-96 overflow-auto whitespace-pre rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{current.content}</pre>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
