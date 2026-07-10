import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { Bot, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
import { useAgents } from "@/hooks/useAgent";
import { useAssistantStore, type AssistantForm } from "@/store/assistantStore";

// Shown instantly while the chat is empty -- no agent turn spent on it,
// unlike an auto-sent greeting (tried first, reverted: it always came back
// as a long policy recap instead of a short hello, see git history).
const ASSISTANT_GREETING = "👋 I'm the ForgeHub assistant — ask me anything about how the system works.";

// Silently prepended to the session's first real message (see ChatPane's
// firstMessagePrefix) so the agent reads the manual before its first reply,
// without a separate canned turn the user has to scroll past. Portuguese,
// matching the manual's own language.
const MANUAL_GROUNDING_NOTE =
  'Contexto: você é o assistente embutido do ForgeHub nesta tela. Antes de responder, leia ' +
  '/root/project/forgehub/docs/MANUAL.md (seção "Política do Assistente") para saber o que você pode ' +
  "e não pode fazer.";

// ```forgehub-fill\n{...}\n``` -- the only channel the agent has to touch
// the screen (see AssistantForm's docstring): it never gets DOM/React
// access, it just replies with this fence and AssistantDrawer applies the
// JSON to whichever form registered itself. Never auto-submits anything.
const FILL_FENCE_RE = /```forgehub-fill\s*\n([\s\S]*?)```/;

function buildFormInstruction(form: AssistantForm): string {
  const fieldLines = form.fields
    .map((f) => `- ${f.name} (${f.label}${f.hint ? `, ${f.hint}` : ""})`)
    .join("\n");
  const exampleField = form.fields[0]?.name ?? "campo";
  return (
    `\n\nHá um formulário aberto nesta tela agora: "${form.description}". Se o usuário pedir para você ` +
    "preenchê-lo, responda com um bloco de código cercado por ```forgehub-fill contendo um objeto JSON " +
    "mapeando os campos abaixo para os valores -- isso preenche o formulário na tela automaticamente. " +
    "Você pode escrever texto normal antes ou depois do bloco. Nunca envie/salve o formulário sozinho -- " +
    "quem confirma a ação é sempre o usuário.\n\n" +
    `Campos disponíveis:\n${fieldLines}\n\n` +
    `Exemplo:\n\`\`\`forgehub-fill\n{"${exampleField}": "valor"}\n\`\`\``
  );
}

/**
 * The single, global Assistant panel -- rendered once by AppLayout as a
 * flex sibling of `<main>` (so opening it shrinks the page instead of
 * floating on top and covering it), triggered by the round button AppLayout
 * also renders. Every page gets it for free; a page opts into a "Use
 * current X" button by calling useAssistantContext (src/hooks/useAssistant.ts)
 * instead of rendering this component itself.
 *
 * `tabId` is derived from the route, not passed in: it scopes the drawer's
 * draft/attachments per page (staging survives open/close) and, combined
 * with `epoch` in this component's key, forces a fresh session whenever
 * you navigate to a different page while the panel is open -- a
 * conversation grounded in Docs' context shouldn't silently continue once
 * you're looking at the Inbox instead.
 */
export function AssistantDrawer() {
  const open = useAssistantStore((s) => s.open);
  const setOpen = useAssistantStore((s) => s.setOpen);
  const context = useAssistantStore((s) => s.context);
  const pendingSeed = useAssistantStore((s) => s.pendingSeed);
  const setPendingSeed = useAssistantStore((s) => s.setPendingSeed);
  const pendingAgentId = useAssistantStore((s) => s.pendingAgentId);
  const setPendingAgentId = useAssistantStore((s) => s.setPendingAgentId);
  const tabId = `assistant:${useLocation().pathname}`;

  // Bumping the epoch remounts ChatPane so initialComposerText re-applies
  // (staged text otherwise wins -- see ChatPane's per-tab staging maps).
  const [epoch, setEpoch] = useState(0);
  const [seed, setSeed] = useState<string | undefined>(undefined);
  const [agentId, setAgentId] = useState<string | null>(null);

  // A page pushed a one-shot message (e.g. "send this cron job's script to
  // the assistant") via setPendingSeed + setOpen(true) -- apply it exactly
  // like the "Use current X" button does, then clear it so it can't replay
  // on a later, unrelated open. A companion pendingAgentId (e.g. a tool's
  // responsible agent) pins which agent the panel targets, if provided.
  useEffect(() => {
    if (!open || pendingSeed == null) return;
    clearChatTabStaging(tabId);
    setSeed(pendingSeed);
    setEpoch((e) => e + 1);
    setPendingSeed(null);
    if (pendingAgentId != null) {
      setAgentId(pendingAgentId);
      setPendingAgentId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pendingSeed]);
  const { data: allAgents } = useAgents();
  const chatableAgents = useMemo(
    () => (allAgents ?? []).filter((a) => Boolean(a.profile_slug)),
    [allAgents]
  );
  const effectiveAgentId = agentId ?? chatableAgents[0]?.id;

  function onClose() {
    setOpen(false);
  }

  // Esc closes the panel, same convention as the app's other overlays
  // (ConfirmDialog, the Docs file viewers).
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleUseContext() {
    const built = context?.build();
    if (!built) return;
    clearChatTabStaging(tabId);
    setSeed(built);
    setEpoch((e) => e + 1);
  }

  // The form section is appended fresh each render (context.form can come
  // and go as the user opens/closes a dialog) -- cheap string work, and
  // this only actually gets sent once, on the session's first message.
  const firstMessagePrefix = context?.form
    ? MANUAL_GROUNDING_NOTE + buildFormInstruction(context.form)
    : MANUAL_GROUNDING_NOTE;

  function handleAssistantMessage(content: string) {
    const form = context?.form;
    if (!form) return;
    const match = content.match(FILL_FENCE_RE);
    if (!match) return;
    try {
      const values = JSON.parse(match[1]);
      if (values && typeof values === "object") form.onFill(values);
    } catch {
      // Agent produced malformed JSON in the fence -- ignore rather than
      // crash the chat; it can retry when the user points it out.
    }
  }

  if (!open) return null;

  return (
    // A normal flex sibling of `<main>` (see AppLayout), not `fixed`:
    // opening it shrinks the page content instead of floating on top and
    // covering it.
    <div className="flex h-full w-full max-w-xl shrink-0 flex-col border-l border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Bot className="h-4 w-4" /> Assistant
        </p>
        <div className="flex items-center gap-1.5">
          {context && (
            <Button
              size="sm"
              variant="outline"
              title="Fills the chat with the screen's context for the agent to work on"
              onClick={handleUseContext}
            >
              📄 {context.label}
            </Button>
          )}
          <Button
            variant="outline"
            size="icon"
            className="shrink-0"
            aria-label="Close assistant"
            title="Close assistant"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {/* ChatPane's root is `absolute inset-0` (it assumes a positioned
          ancestor, true in the Workspace tab layout it was extracted
          from) -- `relative` here gives it that, otherwise the inset-0
          would resolve against the nearest positioned ancestor further up
          the tree instead of this panel, covering unrelated page chrome. */}
      <div className="relative min-h-0 flex-1">
        {effectiveAgentId ? (
          <ChatPane
            key={`${tabId}-${epoch}`}
            tabId={tabId}
            active
            agentId={effectiveAgentId}
            chatableAgents={chatableAgents}
            onAgentChange={setAgentId}
            initialComposerText={seed}
            historyCollapsed
            artifactsOpen={false}
            workingDir={context?.workingDir}
            startNewSession
            emptyStateText={ASSISTANT_GREETING}
            firstMessagePrefix={firstMessagePrefix}
            onAssistantMessage={handleAssistantMessage}
          />
        ) : (
          <p className="p-4 text-sm text-muted-foreground">No agent with a profile available.</p>
        )}
      </div>
    </div>
  );
}
