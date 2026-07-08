import { useEffect, useMemo, useState } from "react";
import { Bot, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
import { useAgents } from "@/hooks/useAgent";

/**
 * The single ChatPane opened as a right-side drawer on any page, to help
 * create content and fill screens without leaving them. `tabId` scopes the
 * drawer's draft/attachments per page (staging survives open/close);
 * `buildContext` produces the screen's context (e.g. the open doc) that
 * "Usar contexto" seeds into a fresh composer.
 */
export function AssistantDrawer({
  tabId,
  buildContext,
  contextLabel,
  workingDir,
}: {
  tabId: string;
  buildContext?: () => string | null;
  contextLabel?: string;
  workingDir?: string;
}) {
  const [open, setOpen] = useState(false);
  // Bumping the epoch remounts ChatPane so initialComposerText re-applies
  // (staged text otherwise wins -- see ChatPane's per-tab staging maps).
  const [epoch, setEpoch] = useState(0);
  const [seed, setSeed] = useState<string | undefined>(undefined);
  const { data: allAgents } = useAgents();
  const chatableAgents = useMemo(
    () => (allAgents ?? []).filter((a) => Boolean(a.profile_slug)),
    [allAgents]
  );
  const [agentId, setAgentId] = useState<string | null>(null);
  const effectiveAgentId = agentId ?? chatableAgents[0]?.id;

  // Esc closes the drawer, same convention as the app's other overlays
  // (ConfirmDialog, the Docs file viewers).
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  function handleUseContext() {
    const context = buildContext?.();
    if (!context) return;
    clearChatTabStaging(tabId);
    setSeed(context);
    setEpoch((e) => e + 1);
  }

  return (
    <>
      {!open && (
        <Button
          size="icon"
          variant="default"
          className="fixed bottom-6 right-6 z-40 rounded-full shadow-lg"
          onClick={() => setOpen(true)}
          aria-label="Abrir assistente"
          title="Abrir assistente"
        >
          <Bot className="h-5 w-5" />
        </Button>
      )}
      {open && (
        <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-xl flex-col border-l border-border bg-background shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <p className="flex items-center gap-2 text-sm font-medium">
              <Bot className="h-4 w-4" /> Assistente
            </p>
            <div className="flex items-center gap-1.5">
              {buildContext && (
                <Button
                  size="sm"
                  variant="outline"
                  title="Preenche o chat com o contexto da tela para o agente trabalhar nele"
                  onClick={handleUseContext}
                >
                  📄 {contextLabel ?? "Usar contexto"}
                </Button>
              )}
              <Button
                variant="outline"
                size="icon"
                className="shrink-0"
                aria-label="Fechar assistente"
                title="Fechar assistente"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          {/* ChatPane's root is `absolute inset-0` (it assumes a positioned
              ancestor, true in the Workspace tab layout it was extracted
              from). Without `relative` here, that inset-0 skips this div
              (not a positioning context) and resolves against the drawer's
              own `fixed` box instead -- covering this panel's header,
              including the close button, entirely. */}
          <div className="relative min-h-0 flex-1">
            {effectiveAgentId ? (
              <ChatPane
                key={epoch}
                tabId={tabId}
                active
                agentId={effectiveAgentId}
                chatableAgents={chatableAgents}
                onAgentChange={setAgentId}
                initialComposerText={seed}
                historyCollapsed
                artifactsOpen={false}
                workingDir={workingDir}
              />
            ) : (
              <p className="p-4 text-sm text-muted-foreground">Nenhum agente com profile disponível.</p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
