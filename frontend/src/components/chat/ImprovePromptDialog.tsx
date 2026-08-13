import { useTranslation } from "react-i18next";
import { Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useImprovePromptViewModel } from "@/hooks/useImprovePromptViewModel";
import { AgentMentionPicker, SlashCommandPicker } from "@/components/chat/ChatPane";
import type { Agent } from "@/hooks/useAgent";

/** View for agent/orchestrator-assisted prompt rewriting -- opened from the
 * Sparkles icon left of the mic button in both ChannelPane.tsx (Channels,
 * shipped first, 2026-08-06) and ChatPane.tsx (Conversations, 2026-08-07).
 * Extracted into a shared component (2026-08-07, Marcelo: "crie um
 * componente dessa tela que será utilizado nos dois chat conversation e
 * canal") once both call sites turned out identical except for their
 * copy. All of that copy now lives in one place too (`chat.json`'s
 * `composer.improvePrompt*` keys, resolved internally via `useTranslation`
 * rather than six-plus translated strings passed down from each caller,
 * 2026-08-07, Marcelo: "no item 3 é melhor fatorar. Porque tenho código
 * repetido") -- a caller only supplies `subject`, the noun/name to
 * interpolate into the shared title template ("the orchestrator" for
 * Channels, the agent's name for a 1:1 chat), since that's the one piece
 * that's genuinely different per caller.
 *
 * All state and behavior (draft/instruction, the rewrite call, the
 * Enter/Escape key rules, the Prompt field's "/"/"#" pickers) live in
 * useImprovePromptViewModel -- this component only renders it (2026-08-07,
 * Marcelo: "precisa seguir padrão de desenvolvimento MVC no código...
 * precisamos adotar padrão de desenvolvimento" -- the org's own
 * `05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md` §21 "ViewModel Hooks",
 * not an invented convention; see that hook's own docstring). Rewrite
 * calls the backend's private rewrite-only route (never a real
 * channel/chat turn, see useStreamImprovePrompt's docstring on either
 * hook) and writes the result back into the Prompt field for review --
 * the dialog only ever reaches the composer (and closes) via OK or
 * Alt+Enter, never automatically when Rewrite finishes (2026-08-07,
 * Marcelo: "Só retorna ao clicar no botão ok ou alt+enter"). Sending the
 * applied text is still a separate, explicit Enter in the composer
 * afterward. */
export function ImprovePromptDialog({
  initialDraft,
  subject,
  agents,
  includeLocalSlashCommands = true,
  includeHermesSlashCommands = true,
  improvePrompt,
  onApply,
  onClose,
}: {
  initialDraft: string;
  /** Already-translated noun/name for the title template, e.g. "the
   * orchestrator" or an agent's name. */
  subject: string;
  /** For the Prompt field's "#" agent-mention picker. */
  agents: Agent[];
  /** Mirrors whichever choice the caller's own main composer already made
   * for its SlashCommandPicker -- ChannelPane passes `false`/`false` (a
   * multi-agent room has no single owning CLI session for /model, /new
   * etc. to act on, same reasoning as ChannelRoom's own composer); Chat's
   * default (`true`/`true`) matches ChatPane's own composer. */
  includeLocalSlashCommands?: boolean;
  includeHermesSlashCommands?: boolean;
  improvePrompt: (draft: string, instruction: string, signal?: AbortSignal) => Promise<string>;
  onApply: (improved: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("chat");
  const {
    status,
    draft,
    instruction,
    errorMessage,
    setInstruction,
    submit,
    applyDraft,
    handleFieldKeyDown,
    slashOpen,
    agentMentionOpen,
    agentMentionQuery,
    promptCommands,
    slashPickerRef,
    agentPickerRef,
    handleDraftChange,
    handleSlashSelect,
    handleAgentMentionSelect,
    closeSlash,
    closeAgentMention,
    handleDraftKeyDown,
  } = useImprovePromptViewModel(initialDraft, improvePrompt, onApply, onClose);
  const submitting = status === "submitting";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby="improve-prompt-title"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="h-1 w-full shrink-0 rounded-t-xl bg-primary/80" />
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-6">
          <div className="flex min-h-0 flex-1 items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
              <h2 id="improve-prompt-title" className="text-base font-semibold leading-tight">
                {t("composer.improvePromptTitle", { subject })}
              </h2>
              {/* Draft field gets most of the dialog's height -- this is
                  where the actual editing happens (2026-08-07, Marcelo:
                  "aumente a tela, ficou muito pequeno a digitação do
                  texto"); the instruction field stays compact. */}
              <div className="mt-4 flex min-h-0 flex-1 flex-col gap-3">
                <div className="flex min-h-0 flex-1 flex-col">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t("composer.improvePromptDraftLabel")}
                  </label>
                  {/* "/" and "#" pickers -- same components/behavior as the
                      channel/chat composer's own (2026-08-07, Marcelo: "ao
                      digitar no campo prompt, precisa interagir igual ao
                      campo prompt do chat do channel"). `placement="down"`
                      opens below (not above like the real composer, see
                      SlashCommandPicker's own docstring) -- but anchored to
                      this zero-height marker right above the (280px+ tall)
                      textarea, not the textarea's own box, so the dropdown
                      lands right under the label instead of past the
                      textarea's bottom edge. That first version rendered
                      outside the modal's scrollable/visible area, so clicks
                      meant for the picker fell through to the backdrop and
                      closed the whole dialog instead (2026-08-07, Marcelo:
                      "se eu criar fora o model ele se fecha" -- "não dá
                      para ver"). */}
                  <div className="relative">
                    {slashOpen && (
                      <SlashCommandPicker
                        ref={slashPickerRef}
                        promptCommands={promptCommands}
                        onSelect={handleSlashSelect}
                        onClose={closeSlash}
                        includeLocal={includeLocalSlashCommands}
                        includeHermes={includeHermesSlashCommands}
                        placement="down"
                      />
                    )}
                    {agentMentionOpen && (
                      <AgentMentionPicker
                        ref={agentPickerRef}
                        agents={agents}
                        query={agentMentionQuery}
                        onSelect={handleAgentMentionSelect}
                        onClose={closeAgentMention}
                        placement="down"
                      />
                    )}
                  </div>
                  <Textarea
                    autoFocus
                    value={draft}
                    onChange={(e) => handleDraftChange(e.target.value)}
                    onKeyDown={handleDraftKeyDown}
                    rows={12}
                    className="min-h-[280px] flex-1 text-base"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t("composer.improvePromptInstructionLabel")}
                  </label>
                  <Textarea
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    onKeyDown={handleFieldKeyDown}
                    placeholder={t("composer.improvePromptInstructionPlaceholder")}
                    rows={2}
                    className="text-sm"
                  />
                </div>
                {status === "error" && errorMessage && <p className="text-xs text-destructive">{errorMessage}</p>}
              </div>
            </div>
          </div>
          <div className="mt-6 flex items-center justify-end gap-3">
            <span className="mr-auto text-[10px] text-muted-foreground">
              {t("composer.improvePromptShortcutHint")}
            </span>
            <Button variant="outline" onClick={onClose} className="min-w-[88px]">
              {t("common:cancel")}
            </Button>
            {/* Applies the draft as typed, no orchestrator call -- the
                button form of Alt+Enter (2026-08-07, Marcelo: "preciso
                adicionar um botão ok para essa ação na tela. porque só tem
                o botão cancel e rewrite"). */}
            <Button variant="outline" onClick={applyDraft} disabled={submitting || !draft.trim()} className="min-w-[88px]">
              {t("composer.improvePromptApply")}
            </Button>
            <Button onClick={submit} disabled={submitting || !draft.trim()} className="min-w-[88px]">
              {submitting && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
              {t("composer.improvePromptConfirm")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
