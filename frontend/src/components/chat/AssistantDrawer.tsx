import { useMemo, useState } from "react";
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
          className="fixed bottom-6 right-6 z-40 gap-2 shadow-lg"
          onClick={() => setOpen(true)}
          aria-label="Abrir assistente"
        >
          <Bot className="h-4 w-4" /> Assistente
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
              <Button variant="ghost" size="icon" aria-label="Fechar assistente" onClick={() => setOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="min-h-0 flex-1">
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
