import { useEffect, useRef, useState } from "react";
import type { Agent } from "@/hooks/useAgent";
import { usePromptCommands, type PromptCommand } from "@/hooks/usePromptCommands";
import type {
  AgentMentionPickerHandle,
  SlashCommandItem,
  SlashCommandPickerHandle,
} from "@/components/chat/ChatPane";

/** ViewModel Hook for ImprovePromptDialog.tsx, per the org's canonical
 * `05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md` §21 ("ViewModel Hooks":
 * use one when a screen has async state, confirmation, and coordination
 * between fields -- this dialog has all three). 2026-08-07, Marcelo:
 * "precisa seguir padrão de desenvolvimento MVC no código... precisamos
 * adotar padrão de desenvolvimento" -- pointed at the existing org
 * standard rather than an invented convention; this hook (and its
 * `status` field below) follows that doc's own worked example
 * (`TitlePaymentViewModel`) shape as closely as this dialog's simpler,
 * single-step flow actually needs -- no `loading`/`ready`/`confirming`
 * states are modeled since there's no initial fetch and no multi-step
 * confirmation here, just `idle → submitting → (closes) | error`.
 *
 * The component (`ImprovePromptDialog.tsx`) renders this ViewModel's
 * fields and calls its actions; it owns no state of its own -- that's the
 * View/ViewModel split the standard calls for (§5.2, §19-21). Piloted
 * here first (smallest, freshest component) before the same split is
 * rolled out to other components incrementally, one screen at a time
 * ("de vagar por tela"), not as a single big-bang rewrite.
 *
 * The Prompt (draft) field's "/" and "#" triggers (2026-08-07, Marcelo:
 * "ao digitar no campo prompt, precisa interagir igual ao campo prompt do
 * chat do channel. quando digitar '/' ou '#' preciso ser as mesmas
 * ações") mirror ChannelRoom's own handleComposerKeyDown/onChange logic
 * verbatim -- ported, not reinvented, since the underlying pickers
 * (SlashCommandPicker/AgentMentionPicker, from ChatPane.tsx) are already
 * shared components. Deliberately scoped to the Prompt field only, not
 * Improvement instruction (Marcelo's own wording: "no campo prompt"). */
export type ImprovePromptStatus = "idle" | "submitting" | "error";

export interface ImprovePromptViewModel {
  status: ImprovePromptStatus;
  draft: string;
  instruction: string;
  errorMessage?: string;
  setInstruction: (value: string) => void;
  /** Rewrites `draft` via `improvePrompt` and writes the result back into
   * `draft` -- the dialog stays open so the result can be reviewed (and
   * re-rewritten, or hand-edited) before it ever reaches the composer;
   * only applyDraft() actually ships it there (2026-08-07, Marcelo: "Só
   * retorna ao clicar no botão ok ou alt+enter"). No-op while already
   * submitting or when the draft is blank. */
  submit(): Promise<void>;
  /** Applies `draft` as-is and closes -- the only path that ever calls
   * onApply()/onClose(), whether `draft` came from typing, from submit(),
   * or both. No-op when the draft is blank (2026-08-07, Marcelo: "no
   * texto do prompt com alt+enter precisa fechar a tela e atualizar o
   * texto no prompt no chat" -- then "preciso adicionar um botão ok para
   * essa ação na tela", so it's both a keyboard shortcut and a button). */
  applyDraft(): void;
  /** Enter in the Improvement instruction field must only ever edit text
   * (browser default for a <textarea>); stopPropagation guards against
   * the channel/chat composer's own "bare Enter sends" binding ever
   * seeing the keystroke, since both live right next to each other.
   * Ctrl/Cmd+Enter is the deliberate, explicit shortcut for submit()
   * instead -- same convention this app already uses on the Database
   * Query/Schema pages (2026-08-07, Marcelo: "ao precionar o enter no
   * campo... envia direto para rewrite" -- "é para alterar o texto").
   * Alt+Enter is the shortcut for applyDraft() -- close-and-apply without
   * asking the orchestrator. */
  handleFieldKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void;

  slashOpen: boolean;
  agentMentionOpen: boolean;
  agentMentionQuery: string;
  promptCommands: PromptCommand[];
  slashPickerRef: React.RefObject<SlashCommandPickerHandle>;
  agentPickerRef: React.RefObject<AgentMentionPickerHandle>;
  /** Draft-field onChange -- like setDraft, but also opens/filters the
   * "/"/"#" pickers as the text changes. */
  handleDraftChange(value: string): void;
  handleSlashSelect(item: SlashCommandItem): void;
  handleAgentMentionSelect(agent: Agent): void;
  closeSlash(): void;
  closeAgentMention(): void;
  /** Draft-field onKeyDown -- picker arrow-key/Enter navigation takes
   * priority over handleFieldKeyDown's Ctrl/Alt+Enter handling, same
   * priority order ChannelRoom's own handleComposerKeyDown uses. */
  handleDraftKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void;
}

export function useImprovePromptViewModel(
  initialDraft: string,
  improvePrompt: (draft: string, instruction: string, signal?: AbortSignal) => Promise<string>,
  onApply: (improved: string) => void,
  onClose: () => void
): ImprovePromptViewModel {
  const [draft, setDraft] = useState(initialDraft);
  const [instruction, setInstruction] = useState("");
  const [status, setStatus] = useState<ImprovePromptStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined);

  const [slashOpen, setSlashOpen] = useState(false);
  const [agentMentionOpen, setAgentMentionOpen] = useState(false);
  const [agentMentionQuery, setAgentMentionQuery] = useState("");
  const { data: promptCommands = [] } = usePromptCommands();
  const slashPickerRef = useRef<SlashCommandPickerHandle>(null);
  const agentPickerRef = useRef<AgentMentionPickerHandle>(null);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Rewrites `draft` in place and keeps the dialog open for review --
  // it used to call onApply()+close immediately, shipping the
  // orchestrator's text straight into the composer with no chance to read
  // it first (2026-08-07, Marcelo: "preciso incluir animações no botão e
  // desabilitar até o final do processo. Só retorna ao clicar no botão ok
  // ou alt+enter" -- the dialog now only ever closes/applies via
  // applyDraft(), whether the draft came from typing, from Rewrite, or
  // both in sequence).
  async function submit() {
    if (!draft.trim() || status === "submitting") return;
    setStatus("submitting");
    setErrorMessage(undefined);
    try {
      const improved = await improvePrompt(draft, instruction);
      setDraft(improved);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setStatus("error");
      return;
    }
    setStatus("idle");
  }

  function applyDraft() {
    if (!draft.trim()) return;
    onApply(draft);
    onClose();
  }

  function handleFieldKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter") return;
    e.stopPropagation();
    if (e.altKey) {
      e.preventDefault();
      applyDraft();
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      void submit();
    }
  }

  // Ported verbatim from ChannelRoom's own composer onChange (see
  // useChannelRoomViewModel.ts) -- "/" as the very first character opens
  // the slash picker, "#" preceded by whitespace/start-of-text opens the
  // agent-mention picker and starts filtering by whatever's typed after it.
  function handleDraftChange(value: string) {
    setDraft(value);
    if (value === "/") {
      setSlashOpen(true);
    } else if (slashOpen && !value.startsWith("/")) {
      setSlashOpen(false);
    }
    const last = value.slice(-1);
    const beforeLast = value.slice(-2, -1);
    if (last === "#" && (beforeLast === "" || /\s/.test(beforeLast))) {
      setAgentMentionOpen(true);
      setAgentMentionQuery("");
    } else if (agentMentionOpen) {
      const hashIndex = value.lastIndexOf("#");
      if (hashIndex === -1 || /\s/.test(value.slice(hashIndex + 1))) {
        setAgentMentionOpen(false);
      } else {
        setAgentMentionQuery(value.slice(hashIndex + 1));
      }
    }
  }

  function handleSlashSelect(item: SlashCommandItem) {
    setSlashOpen(false);
    const text = item.kind === "prompt" ? item.prompt : item.command;
    setDraft(text.endsWith(" ") ? text : `${text} `);
  }

  function handleAgentMentionSelect(agent: Agent) {
    setDraft((prev) => {
      const hashIndex = prev.lastIndexOf("#");
      const base = hashIndex === -1 ? prev : prev.slice(0, hashIndex);
      return `${base}#${agent.name} `;
    });
    setAgentMentionOpen(false);
  }

  function closeSlash() {
    setSlashOpen(false);
  }

  function closeAgentMention() {
    setAgentMentionOpen(false);
  }

  function handleDraftKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (slashOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      slashPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (slashOpen && e.key === "Enter") {
      e.preventDefault();
      slashPickerRef.current?.confirmActive();
      return;
    }
    if (agentMentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      agentPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (agentMentionOpen && e.key === "Enter") {
      e.preventDefault();
      agentPickerRef.current?.confirmActive();
      return;
    }
    if (e.key === "Escape" && (slashOpen || agentMentionOpen)) {
      setSlashOpen(false);
      setAgentMentionOpen(false);
      return;
    }
    handleFieldKeyDown(e);
  }

  return {
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
  };
}
