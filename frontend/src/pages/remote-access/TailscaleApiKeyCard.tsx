/** Remote Access › Tailscale network: the Tailscale API credential ForgeHub
 * uses to generate one single-use auth key per machine when an installer's key
 * is left blank -- never pre-authorized: each machine waits for approval in
 * the Tailscale console (2026-10-20). Only the last 4 characters are shown. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink, KeyRound, Loader2 } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { useRemoveTailscaleApiKey, useSaveTailscaleApiKey, useTailscaleApiKey } from "@/hooks/useVpn";
import { cn } from "@/lib/utils";

const API_KEYS_PAGE = "https://login.tailscale.com/admin/settings/keys";

export function TailscaleApiKeyCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const status = useTailscaleApiKey();
  const save = useSaveTailscaleApiKey();
  const remove = useRemoveTailscaleApiKey();
  const [value, setValue] = useState("");
  const [removing, setRemoving] = useState(false);
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const data = status.data;
  const valid = /^tskey-api-[A-Za-z0-9-]+$/.test(value.trim());

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" aria-hidden="true" /> {t("apiKey.title")}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{t("apiKey.subtitle")}</p>
        </div>
        <a href={API_KEYS_PAGE} target="_blank" rel="noreferrer" className={cn(buttonVariants({ size: "sm", variant: "outline" }), "gap-1.5")}>
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /> {t("apiKey.openConsole")}
        </a>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {status.isLoading && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-label={t("loading")} />}
        {data?.configured ? (
          <div className="flex flex-wrap items-center gap-2">
            <span>{t("apiKey.configured", { hint: data.hint ?? "????" })}</span>
            {data.updated_at && (
              <span className="text-xs text-muted-foreground">{t("apiKey.updated", { who: data.updated_by ?? "—", when: fmt.format(new Date(data.updated_at)) })}</span>
            )}
            <Button type="button" size="sm" variant="ghost" onClick={() => setRemoving(true)} className="ml-auto cursor-pointer text-destructive hover:text-destructive">
              {t("apiKey.remove")}
            </Button>
          </div>
        ) : (
          !status.isLoading && <p className="text-muted-foreground">{t("apiKey.notConfigured")}</p>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input type="password" autoComplete="off" aria-label={t("apiKey.input")} placeholder="tskey-api-…" value={value}
            onChange={(e) => setValue(e.target.value)} className="max-md:text-base" />
          <Button type="button" size="sm" onClick={() => save.mutate(value.trim(), { onSuccess: () => setValue("") })}
            disabled={!valid || save.isPending} className="cursor-pointer gap-1.5">
            {save.isPending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            {t(data?.configured ? "apiKey.replace" : "apiKey.save")}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t("apiKey.help")}</p>
        {save.error && <p role="alert" className="text-xs text-destructive">{save.error.message}</p>}
      </CardContent>
      <ConfirmDialog
        open={removing}
        title={t("apiKey.removeTitle")}
        description={t("apiKey.removeText")}
        confirmLabel={t("apiKey.remove")}
        loading={remove.isPending}
        error={remove.error?.message}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => setRemoving(false) })}
        onCancel={() => setRemoving(false)}
      />
    </Card>
  );
}
