/** Shows a station login's stored password after a confirmation. Every
 * reveal is audited on the backend. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, KeyRound, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
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
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="reveal-title">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 my-auto w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="reveal-title" className="flex items-center gap-2 text-base font-semibold">
            <KeyRound className="h-4 w-4" aria-hidden="true" /> {t(kind === "rustdesk" ? "password.rustdeskTitle" : "password.title", { name: machine.name })}
          </h2>
          <button type="button" onClick={onClose} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="space-y-3 px-6 py-4 text-sm">
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
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onClose} className="cursor-pointer">{t("prepare.close")}</Button>
          {!reveal.data && (
            <Button type="button" size="sm" onClick={() => reveal.mutate(machine.id)} disabled={reveal.isPending} className="cursor-pointer gap-1.5">
              {reveal.isPending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
              {t("password.show")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
