import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api";

const FORGEROUTER_URL =
  (import.meta.env.VITE_FORGEROUTER_URL as string | undefined) ?? "http://localhost:2100";

export default function ForgeRouterPage() {
  // Trusted SSO: exchange our admin session for a ForgeRouter session so the
  // iframe skips its login screen. The token travels in the URL fragment
  // (never hits server logs); on any failure we fall back to the plain URL
  // and ForgeRouter shows its own login. null = exchange still in flight.
  const [ssoToken, setSsoToken] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .post("/api/v1/forgerouter/sso")
      .then((data) => {
        if (!cancelled) setSsoToken((data as { token?: string }).token ?? "");
      })
      .catch(() => {
        if (!cancelled) setSsoToken("");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (ssoToken === null) {
    return (
      <div className="flex h-[calc(100vh-7rem)] items-center justify-center rounded-lg border border-border">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const src = ssoToken ? `${FORGEROUTER_URL}/#sso=${encodeURIComponent(ssoToken)}` : FORGEROUTER_URL;
  return (
    <div className="h-[calc(100vh-7rem)] overflow-hidden rounded-lg border border-border">
      <iframe src={src} title="ForgeRouter" className="h-full w-full" />
    </div>
  );
}
