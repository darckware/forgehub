import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Bot, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
import { useChattableAgents } from "@/hooks/useAgent";
import { useChatLanguage } from "@/hooks/useChatLanguage";
import { useAssistantStore, type AssistantForm } from "@/store/assistantStore";

// The greeting shown while the chat is empty comes from useChatLanguage's
// texts (rendered in the configured response language) -- client-side, no
// agent turn spent on it, unlike an auto-sent greeting (tried first,
// reverted: it always came back as a long policy recap instead of a short
// hello, see git history).

// Opens every assistant session as part of the hidden priming turn (see
// ChatPane's primingMessage) so the agent reads the manual before the
// user's first message even arrives, without a canned turn the user has to
// scroll past. Portuguese, matching the manual's own language.
const MANUAL_GROUNDING_NOTE =
  'Contexto: você é o assistente embutido do ForgeHub nesta tela. Antes de responder, leia ' +
  '/root/project/forgehub/help/MANUAL.md (seção "Política do Assistente") para saber o que você pode ' +
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
  const pendingHiddenContext = useAssistantStore((s) => s.pendingHiddenContext);
  const setPendingHiddenContext = useAssistantStore((s) => s.setPendingHiddenContext);
  const pendingAgentId = useAssistantStore((s) => s.pendingAgentId);
  const setPendingAgentId = useAssistantStore((s) => s.setPendingAgentId);
  const { texts } = useChatLanguage();
  const tabId = `assistant:${useLocation().pathname}`;

  // Bumping the epoch remounts ChatPane so initialComposerText re-applies
  // (staged text otherwise wins -- see ChatPane's per-tab staging maps).
  const [epoch, setEpoch] = useState(0);
  const [seed, setSeed] = useState<string | undefined>(undefined);
  // Screen context attached to the current session, delivered to the agent
  // invisibly via ChatPane's primingMessage (its own hidden opening turn)
  // -- never shown in the composer or the transcript (see assistantStore's
  // pendingHiddenContext).
  const [hiddenContext, setHiddenContext] = useState<string | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);

  // Navigating to another page must not carry the previous page's seed or
  // hidden context into the new page's session -- a conversation grounded
  // in one screen's context shouldn't silently reuse it on another.
  useEffect(() => {
    setSeed(undefined);
    setHiddenContext(null);
  }, [tabId]);

  // A page pushed a one-shot payload via setOpen(true) plus setPendingSeed
  // (visible composer text, e.g. a macro's instructions) and/or
  // setPendingHiddenContext (screen context the agent should get without it
  // cluttering the composer) -- apply it, then clear it so it can't replay
  // on a later, unrelated open. A companion pendingAgentId (e.g. a tool's
  // responsible agent) pins which agent the panel targets, if provided.
  useEffect(() => {
    if (!open || (pendingSeed == null && pendingHiddenContext == null)) return;
    clearChatTabStaging(tabId);
    setSeed(pendingSeed ?? undefined);
    setHiddenContext(pendingHiddenContext);
    setEpoch((e) => e + 1);
    setPendingSeed(null);
    setPendingHiddenContext(null);
    if (pendingAgentId != null) {
      setAgentId(pendingAgentId);
      setPendingAgentId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pendingSeed, pendingHiddenContext]);
  const { data: chatableAgentsData } = useChattableAgents();
  const chatableAgents = chatableAgentsData ?? [];
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

  // "Use current X": attaches the screen's context to a fresh session,
  // invisibly (it goes out as the new session's hidden priming turn via
  // primingMessage) -- it used to paste the built text into the composer,
  // but that noise is internal instruction, not something the user should
  // have to scroll past or accidentally edit.
  function handleUseContext() {
    const built = context?.build();
    if (!built) return;
    clearChatTabStaging(tabId);
    setSeed(undefined);
    setHiddenContext(built);
    setEpoch((e) => e + 1);
  }

  // Sent by ChatPane as the session's own hidden opening turn the moment
  // it mounts (see its primingMessage prop) -- separate from whatever the
  // user types later, so their message goes out clean. The closing note
  // keeps the agent's (equally hidden) reply to it short and action-free.
  // Captured per mount: a context pushed later re-arrives via the pending
  // effect above, which bumps the epoch and remounts ChatPane anyway.
  const primingMessage = [
    MANUAL_GROUNDING_NOTE,
    hiddenContext,
    context?.form ? buildFormInstruction(context.form).trim() : null,
    "Esta é uma mensagem interna de contextualização enviada automaticamente pela interface — o usuário " +
      "não a vê. Não execute nenhuma ação agora: apenas confirme com 'ok' e aguarde a mensagem do usuário.",
  ]
    .filter(Boolean)
    .join("\n\n");

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
              title="Starts a fresh chat with the screen's context attached -- sent to the agent invisibly with your first message"
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
      {/* The attached context itself is invisible by design, so this thin
          strip is the only confirmation the user gets that clicking "Use
          current X" (or a page's send-to-assistant button) did something. */}
      {hiddenContext && (
        <p className="border-b border-border bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground">
          {texts.contextAttached}
        </p>
      )}
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
            emptyStateText={texts.greeting}
            primingMessage={primingMessage}
            onAssistantMessage={handleAssistantMessage}
          />
        ) : (
          <p className="p-4 text-sm text-muted-foreground">No agent with a profile available.</p>
        )}
      </div>
    </div>
  );
}
