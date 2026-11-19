import { useCallback, useEffect, useRef, useState } from "react";
import { isNewVersionAvailable, onVersionCheckRequest } from "@/lib/appVersion";

/** How often an open tab looks for a newer deploy on its own. */
export const VERSION_CHECK_INTERVAL_MS = 5 * 60 * 1000;

export interface NewVersionViewModel {
  status: "idle" | "available";
  reload: () => void;
}

/**
 * MSG-052: polls for a newer build every few minutes, when the tab becomes
 * visible again and whenever a query fails Zod validation (main.tsx's
 * QueryCache), and reports `available` once one is live. Never reloads by
 * itself: the person may be typing.
 */
export function useNewVersionViewModel(check: () => Promise<boolean> = isNewVersionAvailable): NewVersionViewModel {
  const [status, setStatus] = useState<NewVersionViewModel["status"]>("idle");
  const running = useRef(false);

  const run = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      if (await check()) setStatus("available");
    } finally {
      running.current = false;
    }
  }, [check]);

  useEffect(() => {
    if (status === "available") return;
    const timer = window.setInterval(run, VERSION_CHECK_INTERVAL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") void run(); };
    document.addEventListener("visibilitychange", onVisible);
    const unsubscribe = onVersionCheckRequest(() => void run());
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      unsubscribe();
    };
  }, [run, status]);

  return { status, reload: () => window.location.reload() };
}
