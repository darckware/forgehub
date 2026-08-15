import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Mic, Paperclip, RefreshCw, Send, Sparkles, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentSelectorPill, AttachMenuButton } from "@/components/chat/ChatPane";
import { ComposerShell } from "@/components/chat/ComposerShell";
import { ImprovePromptDialog } from "@/components/chat/ImprovePromptDialog";
import {
  type Agent,
  useAgentsTelegramStatus,
  useAgentTelegramConversation,
  useSendAgentTelegramMessage,
  useStreamTelegramImprovePrompt,
} from "@/hooks/useAgent";
import { useTranscribeAudio } from "@/hooks/useChat";
import { cn } from "@/lib/utils";

interface TelegramPaneProps {
  agentId: string;
  agents: Agent[];
  active: boolean;
  onAgentChange: (agentId: string) => void;
}

export function TelegramPane({ agentId, agents, active, onAgentChange }: TelegramPaneProps) {
  const [draft, setDraft] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [deliveryWarning, setDeliveryWarning] = useState<string | null>(null);
  const [improveOpen, setImproveOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  // Toggle for the sync icon (2026-08-15, Marcelo: "o icone de sync tem que
  // funcionar como toogle ativa/desativar") -- independent of `active` (the
  // tab-focus-based signal the polling already respects): this lets an
  // operator explicitly pause polling for a tab that's on screen but not
  // being watched, e.g. to stop background requests while reading a long
  // reply. The initial fetch on mount always happens regardless (that's
  // react-query's own behavior, untouched by refetchInterval).
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const conversation = useAgentTelegramConversation(agentId, active && autoSyncEnabled);
  const sendMessage = useSendAgentTelegramMessage(agentId);
  const improvePrompt = useStreamTelegramImprovePrompt(agentId);
  const transcribe = useTranscribeAudio();
  const { data: statuses } = useAgentsTelegramStatus();
  const agent = agents.find((item) => item.id === agentId);
  // Only agents with a real Telegram channel belong in this switcher
  // (2026-08-15, Marcelo: "só deixe os agentes na seleção do telegram" /
  // "somente os agentes do hermes e openclaw possuem telegram") -- `agents`
  // is the whole chatable roster, which also includes test/preview
  // fixtures and external-CLI runtimes (claude, codex, agy) that have no
  // per-profile .env to hold a bot token in the first place. Both signals
  // are checked: runtime_type narrows to the two runtimes capable of it at
  // all, `installed` (bot token + home channel actually set) narrows to
  // the ones actually configured, not just eligible.
  const telegramAgents = agents.filter(
    (item) =>
      (item.runtime_type === "hermes" || item.runtime_type === "openclaw") &&
      statuses?.agents.some((s) => s.agent_id === item.id && s.installed)
  );
  // The tab's own agent must always be a selectable option, even when it
  // has no Telegram channel of its own (2026-08-15 bugfix) -- a <select>
  // whose value doesn't match any of its <option>s silently renders as
  // whichever option happens to be first, which showed "Scriba" for a tab
  // actually open on Aramis (not Telegram-configured) and made it look
  // like the selector had switched agents on its own. The status badge
  // next to it already communicates "não configurado"; hiding the option
  // entirely instead misrepresents which agent this tab is even about.
  const selectableAgents = agent && !telegramAgents.some((item) => item.id === agent.id)
    ? [agent, ...telegramAgents]
    : telegramAgents;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.data?.messages.length]);

  async function submit() {
    const message = draft.trim();
    const files = attachedFiles;
    if ((!message && files.length === 0) || sendMessage.isPending) return;
    setDraft("");
    setAttachedFiles([]);
    setDeliveryWarning(null);
    try {
      const result = await sendMessage.mutateAsync({ message, files });
      setDeliveryWarning(result.delivery_error ?? null);
    } catch {
      setDraft(message);
      setAttachedFiles(files);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submit();
  }

  function handleFilePick(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (files.length > 0) setAttachedFiles((prev) => [...prev, ...files]);
    event.target.value = "";
  }

  function removeAttachedFile(index: number) {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  }

  // Voice dictation -- same self-contained mechanism ChatPane's/ChannelPane's
  // mic button uses (record -> POST /chat/transcribe -> insert text),
  // agent-agnostic so it's reused as-is (2026-08-15, Marcelo: "igual ao
  // chat/conversation"). The "voice conversation" (live back-and-forth)
  // button is deliberately not added here -- a Telegram relay round-trips
  // through a human's bot on the other end, not a live turn loop.
  async function handleToggleRecording() {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    audioChunksRef.current = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      const result = await transcribe.mutateAsync(blob);
      setDraft((prev) => (prev ? `${prev} ${result.text}` : result.text));
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setIsRecording(true);
  }

  return (
    <section
      className="flex h-full min-h-0 flex-col bg-background"
      aria-label={`Telegram de ${agent?.name ?? "agente"}`}
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {conversation.isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : conversation.isError ? (
          <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">Não foi possível carregar o histórico do Telegram.</p>
        ) : conversation.data?.messages.length ? (
          <div className="flex flex-col gap-3">
            {conversation.data.messages.map((message) => (
              <article
                key={message.id}
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm",
                  message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "mr-auto bg-muted",
                )}
              >
                <div className="mb-1 text-[10px] opacity-70">
                  {message.role === "user" ? "Você · Telegram" : agent?.name ?? "Agente"}
                  {" · "}{new Date(message.timestamp * 1000).toLocaleString()}
                </div>
                {message.content}
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
            <div>
              <Send className="mx-auto mb-2 h-8 w-8" />
              <p>Nenhuma conversa do Telegram encontrada para {agent?.name ?? "este agente"}.</p>
              <p>Envie primeiro uma mensagem ao bot desse agente para estabelecer o canal.</p>
            </div>
          </div>
        )}
      </div>

      <footer className="border-t border-border p-3">
        {deliveryWarning && (
          <p className="mb-2 text-xs text-destructive">
            A resposta foi gravada, mas não pôde ser entregue ao Telegram. Atualize o canal antes de tentar novamente.
          </p>
        )}
        {(sendMessage.error || !conversation.data?.session_id) && (
          <p className={cn("mb-2 text-xs", sendMessage.error ? "text-destructive" : "text-muted-foreground")}>
            {sendMessage.error instanceof Error
              ? sendMessage.error.message
              : !conversation.data?.session_id
                ? "A interação fica disponível depois que o bot receber a primeira mensagem no Telegram."
                : null}
          </p>
        )}
        <div className="flex flex-col gap-2">
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {attachedFiles.map((file, index) => (
                <div key={`${file.name}-${index}`} className="flex w-fit items-center gap-2 rounded-md bg-muted px-2 py-1 text-xs">
                  <Paperclip className="h-3 w-3 shrink-0" />
                  {file.name}
                  <button type="button" aria-label={`Remover ${file.name}`} onClick={() => removeAttachedFile(index)}>
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <ComposerShell
            ref={textareaRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Conversar com ${agent?.name ?? "o agente"} neste canal…`}
            leading={
              <>
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePick} />
                <AttachMenuButton
                  enabledTriggers={[]}
                  onPickFile={() => fileInputRef.current?.click()}
                  onInsertTrigger={() => {}}
                />
              </>
            }
            trailing={
              <>
                <AgentSelectorPill
                  agents={selectableAgents}
                  selectedAgentId={agentId}
                  onSelect={onAgentChange}
                  renderStatus={(item) => {
                    const itemStatus = statuses?.agents.find((s) => s.agent_id === item.id);
                    return (
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-2 py-0.5 text-[11px]",
                          itemStatus?.status === "ok"
                            ? "bg-emerald-500/15 text-emerald-600"
                            : "bg-muted text-muted-foreground",
                        )}
                      >
                        {itemStatus?.status === "ok"
                          ? "canal ativo"
                          : itemStatus?.status === "not_running"
                            ? "gateway parado"
                            : "não configurado"}
                      </span>
                    );
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 rounded-full"
                  aria-label="Melhorar prompt"
                  title="Melhorar prompt"
                  onClick={() => setImproveOpen(true)}
                >
                  <Sparkles className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant={isRecording ? "destructive" : "ghost"}
                  size="icon"
                  className="h-8 w-8 shrink-0 rounded-full"
                  aria-label={isRecording ? "Parar gravação" : "Ditar mensagem por voz"}
                  title={isRecording ? "Parar gravação" : "Ditar mensagem por voz"}
                  onClick={() => void handleToggleRecording()}
                  disabled={transcribe.isPending}
                >
                  {transcribe.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : isRecording ? (
                    <Square className="h-4 w-4" />
                  ) : (
                    <Mic className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className={cn("h-8 w-8 shrink-0 rounded-full", autoSyncEnabled && "text-emerald-600")}
                  aria-label={autoSyncEnabled ? "Desativar atualização automática" : "Ativar atualização automática"}
                  title={autoSyncEnabled ? "Sincronização automática ativa -- clique para desativar" : "Sincronização automática desativada -- clique para ativar"}
                  aria-pressed={autoSyncEnabled}
                  onClick={() => setAutoSyncEnabled((v) => !v)}
                >
                  <RefreshCw className={cn("h-4 w-4", autoSyncEnabled && conversation.isFetching && "animate-spin")} />
                </Button>
                {sendMessage.isPending && (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin self-center text-muted-foreground" aria-label="Enviando" />
                )}
              </>
            }
          />
        </div>
        {improveOpen && (
          <ImprovePromptDialog
            initialDraft={draft}
            subject={agent?.name ?? "o agente"}
            agents={agents}
            includeLocalSlashCommands={false}
            includeHermesSlashCommands={false}
            improvePrompt={improvePrompt}
            onApply={(improved) => {
              setDraft(improved);
              setImproveOpen(false);
              textareaRef.current?.focus();
            }}
            onClose={() => setImproveOpen(false)}
          />
        )}
      </footer>
    </section>
  );
}
