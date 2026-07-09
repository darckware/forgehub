import { useEffect } from "react";
import { useAssistantStore, type AssistantContext } from "@/store/assistantStore";

/**
 * Registers the calling page's "Use current X" context with the global
 * Assistant panel (the round button + drawer rendered once in AppLayout --
 * see AssistantDrawer.tsx). Pass null when there's nothing page-specific
 * to offer (e.g. a page with no Assistant integration at all).
 *
 * Re-registers whenever `context` changes identity (build a new object
 * each render as usual -- this only writes to the store, it doesn't read
 * from it, so it can't loop) and clears on unmount so navigating away
 * doesn't leave a stale builder pointed at an unmounted page's state.
 */
export function useAssistantContext(context: AssistantContext | null) {
  const setContext = useAssistantStore((s) => s.setContext);
  useEffect(() => {
    setContext(context);
    return () => setContext(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context]);
}
