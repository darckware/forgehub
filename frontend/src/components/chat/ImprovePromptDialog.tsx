import { useCallback, useLayoutEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Info, Loader2, Sparkles } from "lucide-react";
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
  improvePrompt: (draft: string, instruction: string, techniqueCode: string, signal?: AbortSignal) => Promise<string>;
  onApply: (improved: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("chat");
  const {
    status,
    draft,
    instruction,
    techniqueCode,
    techniques,
    techniquesLoading,
    recommendedTechniqueCode,
    recommendingTechnique,
    errorMessage,
    setInstruction,
    setTechniqueCode,
    recommendTechnique,
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
  const selectedTechnique = techniques.find((item) => item.code === techniqueCode);
  const categories = Array.from(new Set(techniques.map((item) => item.category)));
  const draftTextareaRef = useRef<HTMLTextAreaElement>(null);

  const resizeDraftTextarea = useCallback(() => {
    const textarea = draftTextareaRef.current;
    if (!textarea) return;

    const minimumHeight = 144;
    const maximumHeight = Math.max(minimumHeight, Math.min(320, window.innerHeight * 0.36));
    textarea.style.height = "auto";
    const contentHeight = textarea.scrollHeight;
    textarea.style.height = `${Math.min(Math.max(contentHeight, minimumHeight), maximumHeight)}px`;
    textarea.style.overflowY = contentHeight > maximumHeight ? "auto" : "hidden";
  }, []);

  useLayoutEffect(() => {
    resizeDraftTextarea();
    window.addEventListener("resize", resizeDraftTextarea);
    return () => window.removeEventListener("resize", resizeDraftTextarea);
  }, [draft, resizeDraftTextarea]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      aria-modal="true"
      role="dialog"
      aria-labelledby="improve-prompt-title"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex h-[90vh] max-h-[860px] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="h-1 w-full shrink-0 rounded-t-xl bg-primary/80" />
        <div className="flex shrink-0 items-center gap-4 px-6 py-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="h-5 w-5 text-primary" />
          </div>
          <h2 id="improve-prompt-title" className="min-w-0 text-base font-semibold leading-tight">
            {t("composer.improvePromptTitle", { subject })}
          </h2>
        </div>

        {/* Only the form body scrolls. The action bar remains outside this
            container so long technique notes can never render underneath
            the buttons. */}
        <div className="min-h-0 flex-1 scroll-smooth overflow-y-scroll overscroll-contain px-6 pb-6 [scrollbar-gutter:stable]">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              {t("composer.improvePromptDraftLabel")}
            </label>
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
              ref={draftTextareaRef}
              autoFocus
              value={draft}
              onChange={(e) => handleDraftChange(e.target.value)}
              onKeyDown={handleDraftKeyDown}
              rows={5}
              className="min-h-[144px] max-h-[36vh] resize-y text-base"
            />
          </div>

          <div className="mt-4">
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

          <div className="mt-4">
            <label htmlFor="prompt-technique" className="mb-1 block text-xs font-medium text-muted-foreground">
              {t("composer.promptTechniqueLabel")}
            </label>
            <div className="flex gap-2">
              <select
                id="prompt-technique"
                value={techniqueCode}
                onChange={(event) => setTechniqueCode(event.target.value)}
                disabled={submitting || techniquesLoading}
                className="h-10 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {categories.map((category) => (
                  <optgroup key={category} label={t(`composer.promptTechniqueCategories.${category}`)}>
                    {techniques.filter((item) => item.category === category).map((item) => (
                      <option key={item.code} value={item.code}>{item.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-10 w-10 shrink-0"
                disabled={submitting || recommendingTechnique || !draft.trim()}
                onClick={() => void recommendTechnique()}
                title={t("composer.promptTechniqueRecommend")}
                aria-label={t("composer.promptTechniqueRecommend")}
              >
                {recommendingTechnique ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              </Button>
            </div>
            {recommendedTechniqueCode && (
              <span className="mt-1 block text-[10px] text-primary">
                {t("composer.promptTechniqueRecommended")}
              </span>
            )}
          </div>

          {selectedTechnique && (
            <div className="mt-3 rounded-lg border border-border/80 bg-muted/35 px-3 py-2.5 text-xs">
              <div className="flex items-center gap-2">
                <Info className="h-3.5 w-3.5 shrink-0 text-primary" />
                <span className="font-semibold">{selectedTechnique.name}</span>
                <span className="ml-auto rounded-full bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                  {t(`composer.promptTechniqueEffort.${selectedTechnique.effort}`)}
                </span>
              </div>
              <p className="mt-1 text-muted-foreground">{selectedTechnique.summary}</p>
              <p className="mt-1"><span className="font-medium">{t("composer.promptTechniqueWhen")}: </span>{selectedTechnique.when_to_use}</p>
              {selectedTechnique.when_to_avoid && (
                <p className="mt-1 text-muted-foreground"><span className="font-medium text-foreground">{t("composer.promptTechniqueAvoid")}: </span>{selectedTechnique.when_to_avoid}</p>
              )}
            </div>
          )}
          {status === "error" && errorMessage && <p className="mt-3 text-xs text-destructive">{errorMessage}</p>}
        </div>

        <div className="flex shrink-0 flex-col gap-3 border-t border-border bg-card px-6 py-4 sm:flex-row sm:items-center">
          <span className="min-w-0 flex-1 text-[10px] text-muted-foreground">
            {t("composer.improvePromptShortcutHint")}
          </span>
          <div className="flex justify-end gap-3">
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
