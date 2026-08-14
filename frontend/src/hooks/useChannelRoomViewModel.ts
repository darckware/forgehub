import { useEffect, useMemo, useRef, useState } from "react";
import type { Agent } from "@/hooks/useAgent";
import { usePromptCommands, type PromptCommand } from "@/hooks/usePromptCommands";
import { useTranscribeAudio } from "@/hooks/useChat";
import {
  useChannel,
  useChannelMessages,
  useStreamChannelMessage,
  useStreamImprovePrompt,
  type ChannelAgentStarted,
  type ChannelAgentStep,
  type ChatChannelMessage,
} from "@/hooks/useChannel";
import type {
  AgentMentionPickerHandle,
  ArtifactMentionPickerHandle,
  ChatQueueStep,
  MentionFilePickerHandle,
  SlashCommandItem,
  SlashCommandPickerHandle,
} from "@/components/chat/ChatPane";

/** ViewModel Hook for ChannelRoom (the transcript + composer half of
 * ChannelPane.tsx) -- Wave 1 of `docs/architecture/
 * FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` (2026-08-07, Marcelo: "faça o item
 * 1"). Covers this screen's composer/draft state and its send/streaming +
 * per-agent `runningAgents` state (the plan's first two ChannelPane
 * sub-items) in one hook rather than two, since `handleSend` genuinely
 * couples them (it reads `content`, drives `sendingCount`/`runningAgents`,
 * and clears the composer) -- splitting further would just pass the same
 * state back and forth between two hooks. `ChannelHeader`'s own
 * rename/delete/membership state (the plan's third sub-item) is a
 * separate screen region with its own local state and is intentionally
 * NOT covered here; see the migration plan for its own checkbox.
 *
 * i18n strings stay in the View (component), same as
 * `useImprovePromptViewModel.ts` -- `attachmentReadErrorText` is the one
 * exception, needed inside `handleFilePick`'s error branch. */
export interface ChannelRoomViewModel {
  channel: ReturnType<typeof useChannel>["data"];
  allMessages: ChatChannelMessage[];
  agentById: Map<string, Agent>;
  finishedStepsByMessageId: Map<string, ChatQueueStep[]>;

  activeTab: "transcript" | "tasks";
  setActiveTab: (tab: "transcript" | "tasks") => void;

  content: string;
  setContent: (value: string | ((prev: string) => string)) => void;
  sending: boolean;
  sendError: string | null;
  setSendError: (value: string | null) => void;
  runningAgents: Map<string, { name: string; startedAt: number; steps: ChatQueueStep[] }>;
  expandedAgentId: string | null;
  setExpandedAgentId: (value: string | null | ((cur: string | null) => string | null)) => void;

  slashOpen: boolean;
  setSlashOpen: (value: boolean) => void;
  agentMentionOpen: boolean;
  setAgentMentionOpen: (value: boolean) => void;
  agentMentionQuery: string;
  setAgentMentionQuery: (value: string) => void;
  mentionOpen: boolean;
  setMentionOpen: (value: boolean) => void;
  artifactMentionOpen: boolean;
  setArtifactMentionOpen: (value: boolean) => void;
  artifactMentionQuery: string;
  setArtifactMentionQuery: (value: string) => void;
  promptCommands: PromptCommand[];

  composerTextareaRef: React.RefObject<HTMLTextAreaElement>;
  slashPickerRef: React.RefObject<SlashCommandPickerHandle>;
  agentPickerRef: React.RefObject<AgentMentionPickerHandle>;
  mentionPickerRef: React.RefObject<MentionFilePickerHandle>;
  artifactPickerRef: React.RefObject<ArtifactMentionPickerHandle>;
  fileInputRef: React.RefObject<HTMLInputElement>;

  handleComposerKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleSlashSelect: (item: SlashCommandItem) => void;
  handleAgentMentionSelect: (agent: Agent) => void;
  handleMentionSelect: (path: string) => void;
  handleArtifactMentionSelect: (path: string) => void;
  handleFilePick: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;

  isRecording: boolean;
  isTranscribing: boolean;
  handleToggleRecording: () => Promise<void>;

  improveOpen: boolean;
  setImproveOpen: (value: boolean) => void;
  improvePrompt: (draft: string, instruction: string, signal?: AbortSignal) => Promise<string>;
}

/** Turno em voo preservado fora do React, por canal (2026-08-13).
 *
 * Alternar Conversas <-> Canais já era seguro desde 2026-08-07 (o painel fica
 * `hidden`, não desmonta). Sair do Workspace inteiro e voltar é outra coisa:
 * aí o componente desmonta de verdade e estes quatro estados morriam juntos,
 * enquanto o turno seguia rodando no backend. O usuário voltava e via a
 * conversa parada, sem indicação de que algo ainda estava em curso.
 *
 * Guardado por canal para dois canais em execução não sobrescreverem um ao
 * outro. `runningAgents` vira array na travessia porque um Map não sobrevive
 * a nada além de referência direta -- aqui é referência, mas manter o formato
 * serializável evita uma armadilha se algum dia isso for para storage. */
type ChannelInFlight = {
  liveMessages: ChatChannelMessage[];
  runningAgents: [string, { name: string; startedAt: number; steps: ChatQueueStep[] }][];
  finishedSteps: [string, ChatQueueStep[]][];
  sendingCount: number;
};

const inFlightByChannelId = new Map<string, ChannelInFlight>();

/** Descarta o turno preservado de um canal -- usado quando o próprio usuário
 * encerra o assunto (troca de canal deliberada não conta: aí ele volta). */
export function clearChannelInFlight(channelId: string): void {
  inFlightByChannelId.delete(channelId);
}

export function useChannelRoomViewModel(
  channelId: string,
  agents: Agent[],
  attachmentReadErrorText: string
): ChannelRoomViewModel {
  const { data: channel } = useChannel(channelId);
  const { data: messages = [] } = useChannelMessages(channelId);
  const streamMessage = useStreamChannelMessage(channelId);
  const improvePrompt = useStreamImprovePrompt(channelId);
  // Os quatro estados abaixo são semeados juntos, do mesmo snapshot: eles se
  // referenciam (uma liveMessage tem um agente rodando, que tem um rastro de
  // passos), e restaurar só parte deixaria a tela em um estado que nunca
  // existiu -- pior que não restaurar nada.
  const restored = inFlightByChannelId.get(channelId);
  const [liveMessages, setLiveMessages] = useState<ChatChannelMessage[]>(
    () => restored?.liveMessages ?? []
  );
  const [content, setContent] = useState("");
  // Count of turns currently in flight, not a single boolean -- multiple
  // messages can be sent back to back without waiting for a previous one
  // to finish (2026-08-07, Marcelo: "solicitado que sejam enviadas várias
  // solicitações para os agentes, com multitarefas... enviar várias
  // solicitações por agentes" -- deliberately parallel, no client-side
  // queue: each Enter starts its own independent stream immediately).
  // `sending` stays a derived boolean so the rest of the render (working
  // strip, etc.) doesn't need to change.
  const [sendingCount, setSendingCount] = useState(() => restored?.sendingCount ?? 0);
  const sending = sendingCount > 0;
  const [sendError, setSendError] = useState<string | null>(null);
  // Which mentioned/broadcast agents are currently mid-turn, keyed by agent
  // id -- populated from the stream's `agent_started` events (all fired up
  // front, since every mentioned agent is launched concurrently) and
  // cleared as each one's real reply arrives via onMessage below
  // (2026-08-06, Marcelo: "o chat do canal deve executar vários agentes ao
  // mesmo tempo... precisa ver a quantidade de processos em paralelo...
  // com o detalhamento de cada agente"). Powers the per-agent "working"
  // strip in place of the old single generic spinner. `steps` fills in
  // live from `agent_step` events (2026-08-06, Marcelo: "traz o passo a
  // passo de ferramentas em tempo real também") -- same ChatQueueStep
  // shape ChatPane's own QueueStepsList/FinishedStepsTrail already render,
  // reused here rather than reimplemented.
  const [runningAgents, setRunningAgents] = useState<
    Map<string, { name: string; startedAt: number; steps: ChatQueueStep[] }>
  >(() => new Map(restored?.runningAgents ?? []));
  // Which running agent's step trail is expanded (click to toggle) --
  // at most one at a time, mirroring FinishedStepsTrail's own
  // single-thread collapse pattern.
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);
  // Once a turn finishes, its step trail is kept keyed by the message it
  // produced (not thrown away with the runningAgents entry) so it stays
  // visible under that message -- "process detail and response are
  // separate, don't erase the process detail" (2026-07-29, Marcelo,
  // ChatPane's own finishedStepsByMessageId precedent).
  const [finishedStepsByMessageId, setFinishedStepsByMessageId] = useState<Map<string, ChatQueueStep[]>>(
    () => new Map(restored?.finishedSteps ?? [])
  );
  // Espelha o turno em voo fora do React a cada mudança -- é o que estará
  // disponível se o componente desmontar no meio. Só grava enquanto há algo
  // acontecendo: um canal ocioso não deve deixar entrada para trás, senão o
  // mapa cresce com o histórico de todo canal já aberto.
  useEffect(() => {
    const busy = sendingCount > 0 || runningAgents.size > 0 || liveMessages.length > 0;
    if (busy) {
      inFlightByChannelId.set(channelId, {
        liveMessages,
        runningAgents: [...runningAgents.entries()],
        finishedSteps: [...finishedStepsByMessageId.entries()],
        sendingCount,
      });
    } else {
      inFlightByChannelId.delete(channelId);
    }
  }, [channelId, liveMessages, runningAgents, finishedStepsByMessageId, sendingCount]);

  const [improveOpen, setImproveOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"transcript" | "tasks">("transcript");
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Same composer picker components ChatPane (Workspace/Conversas) uses,
  // wired the same way -- reused, not reimplemented, so a PromptCommand
  // added anywhere (e.g. /skills-task) shows up here too (2026-08-06,
  // Marcelo: "a '/' não está aparecendo os comandos que sugerimos... por
  // esse motivo que queria o mesmo componente do chat de conversa igual
  // ao do workspace, no chat do canal" -- "seja um desenvolvedor
  // profissional, não economize código"). MentionFilePicker (@) and
  // ArtifactMentionPicker ($) turned out to already be
  // session/channel-agnostic (generic host filesystem browse and a
  // cross-session artifact search, respectively -- see their own
  // docstrings in ChatPane.tsx), so both are wired in too. "!" direct
  // bash command is deliberately left out of AttachMenuButton's menu
  // below (enabledTriggers) -- it has no single owning agent/session in
  // a multi-agent room.
  const [slashOpen, setSlashOpen] = useState(false);
  const [agentMentionOpen, setAgentMentionOpen] = useState(false);
  const [agentMentionQuery, setAgentMentionQuery] = useState("");
  const [mentionOpen, setMentionOpen] = useState(false);
  const [artifactMentionOpen, setArtifactMentionOpen] = useState(false);
  const [artifactMentionQuery, setArtifactMentionQuery] = useState("");
  const [attachmentNames, setAttachmentNames] = useState<string | undefined>(undefined);
  const slashPickerRef = useRef<SlashCommandPickerHandle>(null);
  const agentPickerRef = useRef<AgentMentionPickerHandle>(null);
  const mentionPickerRef = useRef<MentionFilePickerHandle>(null);
  const artifactPickerRef = useRef<ArtifactMentionPickerHandle>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { data: promptCommands = [] } = usePromptCommands();

  // Voice dictation -- same self-contained mechanism ChatPane's mic button
  // uses (record -> POST /chat/transcribe -> insert text), agent-agnostic
  // so it's reused as-is, not reimplemented (2026-08-06, Marcelo: "adicione
  // no campo prompt de comando do canal... icone de voz para ditar o
  // texto. Igual ao do chat de conversação"). The "voice conversation"
  // (live back-and-forth) button is deliberately NOT added -- that one is
  // locked to a single target agent, which doesn't map to a multi-agent
  // room the same way.
  const [isRecording, setIsRecording] = useState(false);
  const transcribe = useTranscribeAudio();
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

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
      setContent((prev) => (prev ? `${prev} ${result.text}` : result.text));
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setIsRecording(true);
  }

  const allMessages = useMemo(() => {
    const seen = new Set(messages.map((m) => m.id));
    return [...messages, ...liveMessages.filter((m) => !seen.has(m.id))];
  }, [messages, liveMessages]);

  // liveMessages used to be reset to [] at the start of every handleSend --
  // that stopped being safe once sends can overlap (a reset would drop a
  // still-unsynced message from another in-flight turn). Instead, prune
  // whatever the query refetch (triggered by each stream's own `finally`)
  // has already folded into `messages`, so the buffer doesn't grow forever
  // over a long-lived channel session.
  useEffect(() => {
    if (liveMessages.length === 0) return;
    const serverIds = new Set(messages.map((m) => m.id));
    setLiveMessages((prev) => {
      const pruned = prev.filter((m) => !serverIds.has(m.id));
      return pruned.length === prev.length ? prev : pruned;
    });
  }, [messages]);

  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);

  function handleComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
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
    if (mentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      mentionPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (mentionOpen && e.key === "Enter") {
      e.preventDefault();
      mentionPickerRef.current?.confirmActive();
      return;
    }
    if (artifactMentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      artifactPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (artifactMentionOpen && e.key === "Enter") {
      e.preventDefault();
      artifactPickerRef.current?.confirmActive();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
      return;
    }
    if (e.key === "Escape" && (slashOpen || agentMentionOpen || mentionOpen || artifactMentionOpen)) {
      setSlashOpen(false);
      setAgentMentionOpen(false);
      setMentionOpen(false);
      setArtifactMentionOpen(false);
    }
  }

  function handleSlashSelect(item: SlashCommandItem) {
    setSlashOpen(false);
    // No "local" kind ever reaches here (excluded via includeLocal=false
    // below) -- always insert text, same as ChatPane's "hermes"/"prompt"
    // branch.
    const text = item.kind === "prompt" ? item.prompt : item.command;
    setContent(text.endsWith(" ") ? text : `${text} `);
    composerTextareaRef.current?.focus();
  }

  function handleAgentMentionSelect(agent: Agent) {
    setContent((prev) => {
      const hashIndex = prev.lastIndexOf("#");
      const base = hashIndex === -1 ? prev : prev.slice(0, hashIndex);
      return `${base}#${agent.name} `;
    });
    setAgentMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  function handleMentionSelect(path: string) {
    setContent((prev) => (prev.endsWith("@") ? prev.slice(0, -1) : prev) + `${path} `);
    setMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  function handleArtifactMentionSelect(path: string) {
    setContent((prev) => {
      const dollarIndex = prev.lastIndexOf("$");
      const base = dollarIndex === -1 ? prev : prev.slice(0, dollarIndex);
      return `${base}${path} `;
    });
    setArtifactMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  // Text-only for now (2026-08-06, Marcelo confirmed via AskUserQuestion:
  // "Só arquivo de texto agora") -- reads the file client-side and pastes
  // its content into the message, same framing ChatPane's server-side
  // non-image branch already uses, so no new backend upload endpoint is
  // needed. Image support (would need the channel turn to also call the
  // bridge's image endpoint) is left for a follow-up.
  async function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    let text: string;
    try {
      text = await file.text();
    } catch {
      setSendError(attachmentReadErrorText);
      return;
    }
    const block = `Conteúdo do arquivo "${file.name}" colado abaixo:\n---\n${text}\n---`;
    setContent((prev) => (prev.trim() ? `${prev}\n\n${block}` : block));
    setAttachmentNames((prev) => (prev ? `${prev}, ${file.name}` : file.name));
    composerTextareaRef.current?.focus();
  }

  function handleAgentStarted(agent: ChannelAgentStarted) {
    setRunningAgents((prev) => {
      const next = new Map(prev);
      next.set(agent.agent_id, { name: agent.agent_name, startedAt: Date.now(), steps: [] });
      return next;
    });
  }

  // Same tool_start/tool_complete -> ChatQueueStep mapping ChatPane.tsx's
  // own handleStreamEvent uses (a new step entry on start, patched in
  // place by tool_id on complete) -- see ChannelAgentStep's docstring for
  // why the wire shape matches.
  function handleAgentStep(step: ChannelAgentStep) {
    setRunningAgents((prev) => {
      const info = prev.get(step.agent_id);
      if (!info) return prev;
      const next = new Map(prev);
      if (!step.done) {
        next.set(step.agent_id, {
          ...info,
          steps: [
            ...info.steps,
            { id: step.tool_id, name: step.name, label: step.context || step.name, detail: step.detail, done: false },
          ],
        });
      } else {
        next.set(step.agent_id, {
          ...info,
          steps: info.steps.map((s) =>
            s.id === step.tool_id
              ? { ...s, label: step.summary || s.label, done: true, demandNumber: step.demand_number }
              : s
          ),
        });
      }
      return next;
    });
  }

  function handleLiveMessage(message: ChatChannelMessage) {
    setLiveMessages((prev) => [...prev, message]);
    // The real reply landing is what actually ends that agent's turn --
    // remove it from the "working" strip the instant its message arrives,
    // not just when the whole stream ends (other mentioned agents may
    // still be mid-turn). Its step trail moves with it, keyed by the new
    // message id, so FinishedStepsTrail can keep showing it afterward.
    // Read via setRunningAgents's own updater (not the `runningAgents`
    // closure captured back when handleSend started this stream) since
    // this callback is invoked from within that same in-flight
    // streamMessage call, well after later re-renders it never sees.
    const authorAgentId = message.author_agent_id;
    if (!authorAgentId) return;
    setRunningAgents((prev) => {
      const info = prev.get(authorAgentId);
      if (!info) return prev;
      if (info.steps.length > 0) {
        setFinishedStepsByMessageId((fs) => {
          const next = new Map(fs);
          next.set(message.id, info.steps);
          return next;
        });
      }
      const next = new Map(prev);
      next.delete(authorAgentId);
      return next;
    });
  }

  async function handleSend() {
    const text = content.trim();
    if (!text) return;
    setContent("");
    const namesToSend = attachmentNames;
    setAttachmentNames(undefined);
    setSendingCount((c) => c + 1);
    setSendError(null);
    // Each call gets its own controller -- unlike the old shared abortRef,
    // this has to survive concurrent in-flight sends without one call's
    // cleanup stepping on another's.
    const controller = new AbortController();
    // Tracks only the agents *this* turn started, so this turn's cleanup
    // never clears a chip that belongs to a different, still-running turn.
    const startedAgentIds = new Set<string>();
    try {
      await streamMessage(
        text,
        handleLiveMessage,
        controller.signal,
        namesToSend,
        (agent) => {
          startedAgentIds.add(agent.agent_id);
          handleAgentStarted(agent);
        },
        handleAgentStep
      );
    } catch (err) {
      // The backend persists whatever succeeded before the error (e.g.
      // the human echo); the message list refetch (triggered in the
      // hook's `finally`) already covers recovering that partial state.
      // What was missing was surfacing the failure itself -- it used to
      // vanish here with nothing shown, the exact "enviei a mensagem e
      // não foi feito nada" symptom (2026-08-06).
      setSendError(err instanceof Error ? err.message : String(err));
    } finally {
      setSendingCount((c) => Math.max(0, c - 1));
      // A failure (or an abort) can leave a straggler that never got its
      // own `data:` message -- don't let its chip linger forever. Only
      // drop chips this turn itself started; a concurrent turn's agents
      // (possibly still running) are left untouched.
      if (startedAgentIds.size > 0) {
        setRunningAgents((prev) => {
          const next = new Map(prev);
          for (const id of startedAgentIds) next.delete(id);
          return next;
        });
      }
    }
  }

  return {
    channel,
    allMessages,
    agentById,
    finishedStepsByMessageId,
    activeTab,
    setActiveTab,
    content,
    setContent,
    sending,
    sendError,
    setSendError,
    runningAgents,
    expandedAgentId,
    setExpandedAgentId,
    slashOpen,
    setSlashOpen,
    agentMentionOpen,
    setAgentMentionOpen,
    agentMentionQuery,
    setAgentMentionQuery,
    mentionOpen,
    setMentionOpen,
    artifactMentionOpen,
    setArtifactMentionOpen,
    artifactMentionQuery,
    setArtifactMentionQuery,
    promptCommands,
    composerTextareaRef,
    slashPickerRef,
    agentPickerRef,
    mentionPickerRef,
    artifactPickerRef,
    fileInputRef,
    handleComposerKeyDown,
    handleSlashSelect,
    handleAgentMentionSelect,
    handleMentionSelect,
    handleArtifactMentionSelect,
    handleFilePick,
    isRecording,
    isTranscribing: transcribe.isPending,
    handleToggleRecording,
    improveOpen,
    setImproveOpen,
    improvePrompt,
  };
}
