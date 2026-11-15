import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { usePreparationDiagnostic } from "@/hooks/useHostInventory";

/** Local recovery path: reading these instructions never depends on working SSH. */
export function PreparationDiagnostic({ serverId }: { serverId: string }) {
  const { t } = useTranslation("remoteAccess");
  const diagnostic = usePreparationDiagnostic(serverId);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(false);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mounted.current = true;
    titleRef.current?.focus();
    titleRef.current?.scrollIntoView?.({ block: "nearest" });
    return () => {
      mounted.current = false;
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  async function copy() {
    if (!diagnostic.data) return;
    setCopyFailed(false);
    try {
      await navigator.clipboard.writeText(diagnostic.data.script);
      if (!mounted.current) return;
      setCopied(true);
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      if (mounted.current) setCopyFailed(true);
    }
  }

  return (
    <section id="preparation-diagnostic" aria-labelledby="preparation-diagnostic-title" className="min-w-0 space-y-3 rounded-md border border-border bg-muted/20 p-3">
      <h3 ref={titleRef} id="preparation-diagnostic-title" tabIndex={-1} className="text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t("prepare.diagnostic.title")}
      </h3>
      <p className="text-xs text-muted-foreground">{t("prepare.diagnostic.help")}</p>
      {diagnostic.isPending && <p role="status" className="flex min-h-20 items-center gap-2 text-sm">
        <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />{t("prepare.diagnostic.loading")}
      </p>}
      {diagnostic.isError && <div className="space-y-2">
        <p role="alert" className="text-sm text-destructive">{t("prepare.diagnostic.loadFailed")}</p>
        <Button type="button" size="sm" variant="outline" disabled={diagnostic.isFetching} onClick={() => void diagnostic.refetch()}>{t("prepare.diagnostic.retry")}</Button>
      </div>}
      {diagnostic.data && <>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>{t("prepare.diagnostic.openLocally")}</li>
          <li>{t(diagnostic.data.language === "powershell" ? "prepare.diagnostic.windows" : "prepare.diagnostic.linux")}</li>
          <li>{t("prepare.diagnostic.sendOutput")}</li>
        </ol>
        <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={() => void copy()}>
          {copied ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
          {t(copied ? "prepare.copied" : "prepare.diagnostic.copy")}
        </Button>
        <span role="status" className="sr-only">{copied ? t("prepare.copied") : ""}</span>
        {copyFailed && <p role="alert" className="text-xs text-destructive">{t("prepare.copyFailed")}</p>}
        <pre tabIndex={0} aria-label={t("prepare.diagnostic.scriptLabel")} className="max-h-[40vh] max-w-full overflow-auto whitespace-pre rounded-md border border-border bg-muted/40 p-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{diagnostic.data.script}</pre>
      </>}
    </section>
  );
}
