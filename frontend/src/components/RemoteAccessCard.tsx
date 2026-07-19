import { useState } from "react";
import { useTranslation } from "react-i18next";
import { QRCodeSVG } from "qrcode.react";
import { Check, Copy, Globe, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useRemoteAccessStatus, useStartRemoteAccess, useStopRemoteAccess } from "@/hooks/useRemoteAccess";

export function RemoteAccessCard() {
  const { t } = useTranslation("dashboard");
  const { data, isLoading } = useRemoteAccessStatus();
  const start = useStartRemoteAccess();
  const stop = useStopRemoteAccess();
  const [copied, setCopied] = useState(false);

  const running = data?.status === "running";
  const busy = start.isPending || stop.isPending;

  function handleCopy() {
    if (!data?.url) return;
    navigator.clipboard.writeText(data.url);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="space-y-3">
      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("remoteAccess.loading")}
        </div>
      )}
      {!isLoading && (
        <>
          {!running && (
            <p className="text-sm text-muted-foreground">
              {t("remoteAccess.description")}
            </p>
          )}

          {running && data?.url && (
            <>
              <div className="flex items-center gap-2 rounded-md border border-border bg-muted px-3 py-2">
                <Globe className="h-4 w-4 shrink-0 text-muted-foreground" />
                <a
                  href={data.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex-1 truncate text-sm text-primary underline-offset-2 hover:underline"
                >
                  {data.url}
                </a>
                <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0" title={t("remoteAccess.copyLink")} onClick={handleCopy}>
                  {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <div className="flex justify-center rounded-md bg-white p-3">
                <QRCodeSVG value={data.url} size={160} marginSize={0} />
              </div>
              <p className="text-center text-xs text-muted-foreground">
                {t("remoteAccess.scanQrCode")}
              </p>
            </>
          )}

          <Button
            variant={running ? "outline" : "default"}
            className="w-full"
            disabled={busy}
            onClick={() => (running ? stop.mutate() : start.mutate())}
          >
            {busy ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Globe className="mr-2 h-4 w-4" />
            )}
            {running ? t("remoteAccess.turnOff") : t("remoteAccess.turnOn")}
          </Button>
        </>
      )}
    </div>
  );
}
