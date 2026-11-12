/** Shows a station login's stored password after a confirmation. Every
 * reveal is audited on the backend. Right-hand panel (2026-11-11). */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, KeyRound, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SidePanel } from "@/components/ui/side-panel";
import { useRevealLoginPassword } from "@/hooks/useHostInventory";
import type { Server } from "@/hooks/useServers";

export function RevealPasswordDialog({
  machine,
  onClose,
  kind = "login",
}: {
  machine: Server;
  onClose: () => void;
  kind?: "login" | "rustdesk";
}) {
  const { t } = useTranslation("remoteAccess");
  const reveal = useRevealLoginPassword(kind);
  const [copied, setCopied] = useState(false);

  return (
    <SidePanel
      onClose={onClose}
      busy={reveal.isPending}
      size="md"
      titleId="reveal-title"
      icon={<KeyRound className="h-4 w-4" aria-hidden="true" />}
      title={t(kind === "rustdesk" ? "password.rustdeskTitle" : "password.title", { name: machine.name })}
      closeLabel={t("cancel")}
      bodyClassName="space-y-3 text-sm"
      footer={
        <>
          <Button type="button" variant="outline" size="sm" onClick={onClose} className="cursor-pointer">{t("prepare.close")}</Button>
          {!reveal.data && (
            <Button type="button" size="sm" onClick={() => reveal.mutate(machine.id)} disabled={reveal.isPending} className="cursor-pointer gap-1.5">
              {reveal.isPending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
              {t("password.show")}
            </Button>
          )}
        </>
      }
    >
      {reveal.data ? (
        <>
          <p>{t(kind === "rustdesk" ? "password.rustdeskId" : "password.login")}: <span className="font-mono">{reveal.data.login || "—"}</span></p>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded-md border border-border bg-muted/40 px-3 py-2 font-mono">{reveal.data.password}</code>
            <Button
              type="button"
              size="icon"
              variant="outline"
              aria-label={t("prepare.copy")}
              onClick={() => {
                void navigator.clipboard.writeText(reveal.data!.password);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
              className="cursor-pointer"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
            </Button>
          </div>
        </>
      ) : (
        <p className="text-muted-foreground">{t("password.confirm")}</p>
      )}
      {reveal.isError && <p role="alert" className="text-xs text-destructive">{reveal.error.message}</p>}
    </SidePanel>
  );
}
