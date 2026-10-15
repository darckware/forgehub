/** "Prepare" a station: the one-time script (per OS, carrying the station's
 * key) to paste through RustDesk so the station becomes Ready. */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Loader2, Wrench, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { usePrepareHost } from "@/hooks/useHostInventory";
import type { Server } from "@/hooks/useServers";

export function PrepareDialog({ machine, onClose }: { machine: Server; onClose: () => void }) {
  const { t } = useTranslation("remoteAccess");
  const prepare = usePrepareHost();
  const [copied, setCopied] = useState(false);
  const { mutate } = prepare;

  useEffect(() => {
    mutate(machine.id);
  }, [mutate, machine.id]);

  const data = prepare.data;
  return (
    <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="prepare-title">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 my-auto w-full max-w-3xl rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 id="prepare-title" className="flex items-center gap-2 text-base font-semibold">
            <Wrench className="h-4 w-4" aria-hidden="true" /> {t("prepare.title", { name: machine.name })}
          </h2>
          <button type="button" onClick={onClose} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="space-y-3 px-6 py-4">
          {prepare.isPending ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> {t("prepare.loading")}
            </p>
          ) : prepare.isError ? (
            <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">{prepare.error.message}</p>
          ) : data ? (
            <>
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                <li>{t("prepare.step1")}</li>
                <li>{t(data.language === "powershell" ? "prepare.step2Windows" : "prepare.step2Posix")}</li>
                <li>{t("prepare.step3")}</li>
              </ol>
              {data.key_created && <p className="text-xs text-muted-foreground">{t("prepare.keyCreated")}</p>}
              <div className="relative">
                <pre className="max-h-[50vh] overflow-auto whitespace-pre rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">{data.script}</pre>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="absolute right-2 top-2 cursor-pointer gap-1.5"
                  onClick={() => {
                    void navigator.clipboard.writeText(data.script);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                  {t(copied ? "prepare.copied" : "prepare.copy")}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t("prepare.safeNote")}</p>
            </>
          ) : null}
        </div>
        <div className="flex justify-end border-t border-border px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onClose} className="cursor-pointer">{t("prepare.close")}</Button>
        </div>
      </div>
    </div>
  );
}
