import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Crown,
  Hash,
  Info,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Trash2,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useAgentSkills, useSkills, type Agent } from "@/hooks/useAgent";
import {
  AgentMentionPicker,
  ArtifactMentionPicker,
  AttachMenuButton,
  ChatPane,
  MentionFilePicker,
  SlashCommandPicker,
  type AgentMentionPickerHandle,
  type ArtifactMentionPickerHandle,
  type MentionFilePickerHandle,
  type SlashCommandItem,
  type SlashCommandPickerHandle,
} from "@/components/chat/ChatPane";
import { ComposerShell } from "@/components/chat/ComposerShell";
import { useChatSessions } from "@/hooks/useChat";
import { usePromptCommands } from "@/hooks/usePromptCommands";
import { useProjects } from "@/hooks/useProject";
import { PROJECT_AGENT_ROLES, useProjectMemberships } from "@/hooks/useOrchestration";
import { useApproveApproval, useRejectApproval } from "@/hooks/useGovernance";
import {
  useAddChannelMember,
  useAttachChannelProject,
  useChannel,
  useChannelMessages,
  useChannelTasks,
  useChannels,
  useCreateChannel,
  useCreateChannelTask,
  useDeleteChannel,
  useDetachChannelProject,
  useDispatchChannelMessage,
  usePromoteChannelTask,
  useRemoveChannelMember,
  useStreamChannelMessage,
  useUpdateChannel,
  useUpdateChannelMember,
  useUpdateChannelTask,
  type ChatChannelMember,
  type ChatChannelMessage,
} from "@/hooks/useChannel";

/**
 * A Slack-like room for the logged-in human + N Agent members, sharing one
 * transcript -- distinct from ChatPane's "1 human + 1 owning agent"
 * conversations. See backend db/models/channel.py's module docstring for
 * the full design (member choice is always explicit, project attachment is
 * mutable like adding an MCP, turn_policy is "#mention only").
 */
export function ChannelPane({ agents, defaultProjectId }: { agents: Agent[]; defaultProjectId?: string }) {
  const { t } = useTranslation("workspace");
  const { data: channels = [] } = useChannels();
  const [selectedChannelId, setSelectedChannelId] = useState<string | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  // 2026-08-06, Marcelo: "preciso de adicionar o icone de ocultar a coluna
  // de Channels com a função de toggle de ocultar/expandir" -- persisted
  // like Workspace's own viewMode toggle, so it survives a reload.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem("forgehub-channels-sidebar-collapsed") === "1"
  );
  useEffect(() => {
    localStorage.setItem("forgehub-channels-sidebar-collapsed", sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);
  // Clicking an agent's name in the channel header opens their individual
  // 1:1 session (the existing ChatSession concept, Workspace's own
  // Conversas) in a third column alongside the shared channel -- "igual ao
  // Buzz" (2026-08-06, Marcelo). Deliberately the real per-agent session,
  // not a filtered slice of the channel transcript.
  const [openAgentSession, setOpenAgentSession] = useState<{ id: string; name: string } | null>(null);

  const withProject = channels.filter((c) => c.project_id);
  const withoutProject = channels.filter((c) => !c.project_id);
  // Arriving from a Project's "Abrir canal" handoff (see WorkspacePage's
  // openChannel state) prefers that project's existing channel over
  // whatever would otherwise be first in the list.
  const activeChannelId =
    selectedChannelId ?? channels.find((c) => c.project_id === defaultProjectId)?.id ?? channels[0]?.id;

  // Shares the query cache with ChannelRoom's own useChannelMessages call
  // (same channelId, same key) -- no extra request, just reused here to
  // filter this agent's own turns as grounding context for their
  // individual session (2026-08-06, Marcelo: "é preciso contextualizar
  // com o filtro dos texto deles").
  const { data: channelMessagesForPriming = [] } = useChannelMessages(activeChannelId);
  const { data: openAgentSessions } = useChatSessions(openAgentSession?.id);
  const activeChannel = channels.find((c) => c.id === activeChannelId);
  const agentOwnMessages = openAgentSession
    ? channelMessagesForPriming.filter((m) => m.author_agent_id === openAgentSession.id)
    : [];
  // Only the very first time this agent's individual session is opened --
  // once a real ChatSession exists, resume it normally instead of
  // re-injecting the same grounding turn on every click (would spam a
  // hidden turn into an otherwise-continuous conversation).
  const needsPriming = Boolean(openAgentSession) && openAgentSessions?.length === 0 && agentOwnMessages.length > 0;
  const primingMessage = needsPriming
    ? [
        `Contexto: você (${openAgentSession!.name}) participa do canal "${activeChannel?.name ?? ""}". `
          + "Aqui está o que você já disse lá, para continuarmos a partir daí:",
        agentOwnMessages.map((m) => `- ${m.content}`).join("\n"),
        "Esta é uma mensagem interna de contextualização enviada automaticamente pela interface — o usuário "
          + "não a vê. Não execute nenhuma ação agora: apenas confirme com 'ok' e aguarde a mensagem do usuário.",
      ].join("\n\n")
    : undefined;

  // Arrived pointed at a project with no channel yet -- jump straight to
  // the create form pre-filled with it instead of an empty "select or
  // create" state. Fires once per defaultProjectId handoff.
  const autoCreateHandledRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!defaultProjectId || defaultProjectId === autoCreateHandledRef.current) return;
    if (channels.some((c) => c.project_id === defaultProjectId)) return;
    autoCreateHandledRef.current = defaultProjectId;
    setCreating(true);
  }, [defaultProjectId, channels]);

  return (
    <div className="flex min-h-0 flex-1">
      <div
        className={cn(
          "flex shrink-0 flex-col border-r border-border transition-[width]",
          sidebarCollapsed ? "w-11" : "w-64"
        )}
      >
        <div className={cn("flex items-center px-2 py-2", sidebarCollapsed ? "flex-col gap-1" : "justify-between px-3")}>
          {!sidebarCollapsed && (
            <span className="text-xs font-medium uppercase text-muted-foreground">
              {t("channels.title")}
            </span>
          )}
          <div className={cn("flex items-center gap-1", sidebarCollapsed && "flex-col")}>
            {!sidebarCollapsed && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setCreating(true)}
                aria-label={t("channels.new")}
              >
                <Plus className="h-4 w-4" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => setSidebarCollapsed((v) => !v)}
              aria-label={sidebarCollapsed ? t("channels.expandSidebar") : t("channels.collapseSidebar")}
              title={sidebarCollapsed ? t("channels.expandSidebar") : t("channels.collapseSidebar")}
            >
              {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
            </Button>
            {sidebarCollapsed && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setCreating(true)}
                aria-label={t("channels.new")}
              >
                <Plus className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        {!sidebarCollapsed && (
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            {withProject.length > 0 && (
              <ChannelGroup
                label={t("channels.withProject")}
                items={withProject}
                activeId={activeChannelId}
                onSelect={setSelectedChannelId}
              />
            )}
            {withoutProject.length > 0 && (
              <ChannelGroup
                label={t("channels.freeform")}
                items={withoutProject}
                activeId={activeChannelId}
                onSelect={setSelectedChannelId}
              />
            )}
            {channels.length === 0 && !creating && (
              <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                {t("channels.empty")}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {creating ? (
          <CreateChannelForm
            agents={agents}
            defaultProjectId={defaultProjectId}
            onCreated={(id) => {
              setSelectedChannelId(id);
              setCreating(false);
            }}
            onCancel={() => setCreating(false)}
          />
        ) : activeChannelId ? (
          <ChannelRoom
            key={activeChannelId}
            channelId={activeChannelId}
            agents={agents}
            onOpenAgentSession={setOpenAgentSession}
            onDeleted={() => setSelectedChannelId(undefined)}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            {t("channels.selectOrCreate")}
          </div>
        )}
      </div>

      {/* Third column: the clicked agent's own individual session -- one
          chat component reused from Workspace/Conversas (ChatPane), not a
          second one (2026-08-06, Marcelo: "só para não ter dois componente
          de chat"), just agent-locked (lockAgent hides the agent-selector
          pill since it's already fixed by which name was clicked). */}
      {openAgentSession && (
        <div className="relative flex w-96 shrink-0 flex-col border-l border-border">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-medium">{openAgentSession.name}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => setOpenAgentSession(null)}
              aria-label={t("common:close")}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="relative flex-1">
            {/* Waits for openAgentSessions to resolve before mounting --
                ChatPane decides resume-vs-start-new once, on mount, so
                startNewSession/primingMessage must already be correct the
                first time it renders rather than flipping true after an
                initial false (which would race past its own mount
                effect). */}
            {openAgentSessions === undefined ? (
              <div className="flex h-full items-center justify-center">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ChatPane
                key={openAgentSession.id}
                tabId={`channel-agent-${openAgentSession.id}`}
                active
                agentId={openAgentSession.id}
                chatableAgents={agents}
                onAgentChange={() => {}}
                historyCollapsed
                artifactsOpen={false}
                lockAgent
                startNewSession={needsPriming}
                primingMessage={primingMessage}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ChannelGroup({
  label,
  items,
  activeId,
  onSelect,
}: {
  label: string;
  items: { id: string; name: string; archived: boolean }[];
  activeId: string | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="mb-2">
      <div className="px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {items.map((c) => (
        <button
          key={c.id}
          onClick={() => onSelect(c.id)}
          className={cn(
            "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm",
            c.id === activeId ? "bg-accent text-accent-foreground" : "hover:bg-accent/60"
          )}
        >
          <Hash className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{c.name}</span>
        </button>
      ))}
    </div>
  );
}

function CreateChannelForm({
  agents,
  defaultProjectId,
  onCreated,
  onCancel,
}: {
  agents: Agent[];
  defaultProjectId?: string;
  onCreated: (channelId: string) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation("workspace");
  const { data: projects = [] } = useProjects();
  const createChannel = useCreateChannel();
  const [name, setName] = useState("");
  const [projectId, setProjectId] = useState(defaultProjectId ?? "");
  const [memberIds, setMemberIds] = useState<string[]>([]);
  // Keyed by agent_id -- prefilled lazily from Agent.default_role the
  // first time each agent is selected, then always editable (2026-08-05,
  // Marcelo: "não seria melhor escolher as funções de cada um nesse
  // momento"). Only entries that actually diverge from -- or set -- a role
  // are sent as member_roles; an agent never added here still falls back
  // to its own default_role server-side.
  const [memberRoles, setMemberRoles] = useState<Record<string, string>>({});
  const [orchestratorId, setOrchestratorId] = useState("");
  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);

  function toggleMember(id: string) {
    setMemberIds((prev) => {
      if (prev.includes(id)) {
        if (orchestratorId === id) setOrchestratorId("");
        return prev.filter((m) => m !== id);
      }
      setMemberRoles((roles) =>
        roles[id] !== undefined ? roles : { ...roles, [id]: agentById.get(id)?.default_role ?? "" }
      );
      return [...prev, id];
    });
  }

  async function handleSubmit() {
    if (!name.trim()) return;
    const roles = Object.fromEntries(
      memberIds.filter((id) => memberRoles[id]).map((id) => [id, memberRoles[id]])
    );
    const result = await createChannel.mutateAsync({
      name: name.trim(),
      project_id: projectId || null,
      member_agent_ids: memberIds,
      member_roles: Object.keys(roles).length > 0 ? roles : undefined,
      orchestrator_agent_id: orchestratorId || null,
    });
    onCreated(result.channel.id);
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-3 overflow-y-auto p-4">
      <h3 className="text-sm font-medium">{t("channels.new")}</h3>
      <Input
        placeholder={t("channels.namePlaceholder")}
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
      <div>
        <label className="mb-1 block text-xs text-muted-foreground">
          {t("channels.projectOptional")}
        </label>
        <Select value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">{t("channels.freeformIdea")}</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </div>
      <div>
        <label className="mb-1 block text-xs text-muted-foreground">
          {t("channels.chooseMembers")}
        </label>
        <div className="flex flex-wrap gap-1.5">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => toggleMember(a.id)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs",
                memberIds.includes(a.id)
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:bg-accent"
              )}
            >
              {a.name}
            </button>
          ))}
        </div>
      </div>
      {memberIds.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md border border-border p-2">
          {memberIds.map((id) => {
            const agent = agentById.get(id);
            if (!agent) return null;
            return (
              <div key={id} className="flex flex-col gap-1 border-b border-border/60 pb-2 last:border-0 last:pb-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium">{agent.name}</span>
                  <Select
                    className="h-6 w-36 text-[11px]"
                    value={memberRoles[id] ?? ""}
                    onChange={(e) => setMemberRoles((roles) => ({ ...roles, [id]: e.target.value }))}
                  >
                    <option value="">{t("channels.noRole")}</option>
                    {PROJECT_AGENT_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role.replace(/_/g, " ")}
                      </option>
                    ))}
                  </Select>
                </div>
                {/* One-line summary of the specialist, so the human isn't
                    picking a function blind (2026-08-05, Marcelo: "adicione
                    um resumo da função de cada especialista"). */}
                {agent.description && (
                  <p className="line-clamp-2 text-[11px] text-muted-foreground">{agent.description}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
      {memberIds.length > 0 && (
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">
            {t("channels.chooseOrchestrator")}
          </label>
          <Select value={orchestratorId} onChange={(e) => setOrchestratorId(e.target.value)}>
            <option value="">{t("channels.noOrchestrator")}</option>
            {memberIds.map((id) => (
              <option key={id} value={id}>
                {agentById.get(id)?.name ?? id}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-[11px] text-muted-foreground">{t("channels.orchestratorHint")}</p>
        </div>
      )}
      <div className="mt-2 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t("common:cancel")}
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={!name.trim() || createChannel.isPending}>
          {createChannel.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("channels.create")}
        </Button>
      </div>
    </div>
  );
}

function ChannelRoom({
  channelId,
  agents,
  onOpenAgentSession,
  onDeleted,
}: {
  channelId: string;
  agents: Agent[];
  onOpenAgentSession: (agent: { id: string; name: string }) => void;
  onDeleted: () => void;
}) {
  const { t } = useTranslation("workspace");
  const { data: channel } = useChannel(channelId);
  const { data: messages = [] } = useChannelMessages(channelId);
  const streamMessage = useStreamChannelMessage(channelId);
  const [liveMessages, setLiveMessages] = useState<ChatChannelMessage[]>([]);
  const [content, setContent] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"transcript" | "tasks">("transcript");
  const abortRef = useRef<AbortController | null>(null);
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

  const allMessages = useMemo(() => {
    const seen = new Set(messages.map((m) => m.id));
    return [...messages, ...liveMessages.filter((m) => !seen.has(m.id))];
  }, [messages, liveMessages]);

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
      handleSend();
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
      setSendError(t("channels.attachmentReadError"));
      return;
    }
    const block = `Conteúdo do arquivo "${file.name}" colado abaixo:\n---\n${text}\n---`;
    setContent((prev) => (prev.trim() ? `${prev}\n\n${block}` : block));
    setAttachmentNames((prev) => (prev ? `${prev}, ${file.name}` : file.name));
    composerTextareaRef.current?.focus();
  }

  async function handleSend() {
    const text = content.trim();
    if (!text || sending) return;
    setContent("");
    const namesToSend = attachmentNames;
    setAttachmentNames(undefined);
    setSending(true);
    setSendError(null);
    setLiveMessages([]);
    abortRef.current = new AbortController();
    try {
      await streamMessage(
        text,
        (message) => setLiveMessages((prev) => [...prev, message]),
        abortRef.current.signal,
        namesToSend
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
      setSending(false);
    }
  }

  if (!channel) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "transcript" | "tasks")} className="flex min-h-0 flex-1 flex-col">
        <ChannelHeader
          channel={channel}
          agents={agents}
          onOpenAgentSession={onOpenAgentSession}
          onDeleted={onDeleted}
          tabs={
            <TabsList>
              <TabsTrigger value="transcript">{t("channels.transcript")}</TabsTrigger>
              <TabsTrigger value="tasks">{t("channels.tasks")}</TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value="transcript" className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {allMessages.map((m) => (
              <MessageBubble key={m.id} message={m} agent={m.author_agent_id ? agentById.get(m.author_agent_id) : undefined} channelId={channelId} />
            ))}
            {allMessages.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("channels.noMessages")}
              </p>
            )}
            {sending && (
              <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t("channels.working")}
              </div>
            )}
          </div>
          {sendError && (
            <div className="mx-3 mb-2 flex items-center justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span>{sendError}</span>
              <button onClick={() => setSendError(null)} aria-label={t("common:close")}>
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="border-t border-border p-3">
            {/* Same composer shell ChatPane (Workspace/Conversas) uses --
                factored into ComposerShell (2026-08-06, Marcelo: "ele iria
                ser fatorado e adiciona as funcionalidades em um só
                componente") so the two chats can't visually drift apart.
                No visible send button, same as ChatPane's own composer
                (2026-08-06, Marcelo: "remove o botão de enviar pelo
                [enter]") -- Enter sends, Shift+Enter inserts a newline. */}
            <ComposerShell
              ref={composerTextareaRef}
              value={content}
              onChange={(e) => {
                const value = e.target.value;
                setContent(value);
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
                if (last === "@" && (beforeLast === "" || /\s/.test(beforeLast))) {
                  setMentionOpen(true);
                }
                if (last === "$" && (beforeLast === "" || /\s/.test(beforeLast))) {
                  setArtifactMentionOpen(true);
                  setArtifactMentionQuery("");
                } else if (artifactMentionOpen) {
                  const dollarIndex = value.lastIndexOf("$");
                  if (dollarIndex === -1 || /\s/.test(value.slice(dollarIndex + 1))) {
                    setArtifactMentionOpen(false);
                  } else {
                    setArtifactMentionQuery(value.slice(dollarIndex + 1));
                  }
                }
              }}
              onKeyDown={handleComposerKeyDown}
              placeholder={t("channels.composerPlaceholder")}
              leading={
                <>
                  {slashOpen && (
                    <SlashCommandPicker
                      ref={slashPickerRef}
                      promptCommands={promptCommands}
                      onSelect={handleSlashSelect}
                      onClose={() => setSlashOpen(false)}
                      includeLocal={false}
                      includeHermes={false}
                    />
                  )}
                  {agentMentionOpen && (
                    <AgentMentionPicker
                      ref={agentPickerRef}
                      agents={agents}
                      query={agentMentionQuery}
                      onSelect={handleAgentMentionSelect}
                      onClose={() => setAgentMentionOpen(false)}
                    />
                  )}
                  {mentionOpen && (
                    <MentionFilePicker
                      ref={mentionPickerRef}
                      rootPath={channel.working_directory_path ?? undefined}
                      onSelectPath={handleMentionSelect}
                      onClose={() => setMentionOpen(false)}
                    />
                  )}
                  {artifactMentionOpen && (
                    <ArtifactMentionPicker
                      ref={artifactPickerRef}
                      query={artifactMentionQuery}
                      onSelectPath={handleArtifactMentionSelect}
                      onClose={() => setArtifactMentionOpen(false)}
                    />
                  )}
                  <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePick} />
                  <AttachMenuButton
                    enabledTriggers={["/", "@", "#", "$"]}
                    onPickFile={() => fileInputRef.current?.click()}
                    onInsertTrigger={(char) => {
                      setContent((prev) => {
                        const needsSpace = prev.length > 0 && !/\s$/.test(prev);
                        return prev + (needsSpace ? " " : "") + char;
                      });
                      if (char === "@") setMentionOpen(true);
                      if (char === "#") {
                        setAgentMentionOpen(true);
                        setAgentMentionQuery("");
                      }
                      if (char === "$") {
                        setArtifactMentionOpen(true);
                        setArtifactMentionQuery("");
                      }
                      if (char === "/") setSlashOpen(true);
                      composerTextareaRef.current?.focus();
                    }}
                  />
                </>
              }
              trailing={
                sending && (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin self-center text-muted-foreground" />
                )
              }
            />
          </div>
        </TabsContent>
        <TabsContent value="tasks" className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <ChannelTasksPanel channelId={channelId} channel={channel} agents={agents} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ChannelHeader({
  channel,
  agents,
  tabs,
  onOpenAgentSession,
  onDeleted,
}: {
  channel: ReturnType<typeof useChannel>["data"];
  agents: Agent[];
  /** Conversation/Tasks TabsList -- rendered inline in the header's first
   * row, right-aligned, instead of on its own row below the member badges
   * (2026-08-06, Marcelo: "mova a aba para mesma linha do nome do canal
   * alinhado a direta. Essa forma libera espaço no chat"). Passed in
   * rather than owned here because the Tabs context (transcript vs tasks
   * content) still lives in the parent ChannelRoom. */
  tabs?: ReactNode;
  /** Clicking an agent's name opens their individual 1:1 session (the
   * same ChatPane the Workspace/Conversas tab uses) in a third column
   * alongside the channel -- "igual ao Buzz" (2026-08-06). */
  onOpenAgentSession: (agent: { id: string; name: string }) => void;
  /** Fires after a successful delete so the parent can clear its selected
   * channel id (2026-08-06, Marcelo: "adicione o icone de editar e
   * excluir o canal"). */
  onDeleted: () => void;
}) {
  const { t } = useTranslation("workspace");
  const { data: projects = [] } = useProjects();
  const attachProject = useAttachChannelProject();
  const detachProject = useDetachChannelProject();
  const addMember = useAddChannelMember(channel!.id);
  const removeMember = useRemoveChannelMember(channel!.id);
  const updateMember = useUpdateChannelMember(channel!.id);
  const updateChannel = useUpdateChannel();
  const deleteChannel = useDeleteChannel();
  const [pickingProject, setPickingProject] = useState(false);
  const [pickingAgent, setPickingAgent] = useState(false);
  const [detailMemberId, setDetailMemberId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  if (!channel) return null;
  const project = projects.find((p) => p.id === channel.project_id);
  const memberAgentIds = new Set(channel.members.filter((m) => !m.is_human).map((m) => m.agent_id));
  const addableAgents = agents.filter((a) => !memberAgentIds.has(a.id));

  function startEditingName() {
    setNameDraft(channel!.name);
    setEditingName(true);
  }

  function commitNameEdit() {
    const trimmed = nameDraft.trim();
    setEditingName(false);
    if (trimmed && trimmed !== channel!.name) {
      updateChannel.mutate({ channelId: channel!.id, name: trimmed });
    }
  }

  function handleDeleteChannel() {
    if (!window.confirm(t("channels.confirmDelete", { name: channel!.name }))) return;
    deleteChannel.mutate(channel!.id, { onSuccess: onDeleted });
  }

  return (
    <div className="border-b border-border px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Hash className="h-4 w-4 shrink-0 text-muted-foreground" />
        {editingName ? (
          <Input
            autoFocus
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={commitNameEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitNameEdit();
              if (e.key === "Escape") setEditingName(false);
            }}
            className="h-7 w-48 text-sm font-medium"
          />
        ) : (
          <span className="font-medium">{channel.name}</span>
        )}
        {!editingName && (
          <>
            <button
              onClick={startEditingName}
              aria-label={t("channels.renameChannel")}
              title={t("channels.renameChannel")}
              className="text-muted-foreground hover:text-foreground"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleDeleteChannel}
              aria-label={t("channels.deleteChannel")}
              title={t("channels.deleteChannel")}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        {project ? (
          <Badge variant="secondary" className="gap-1">
            {project.name}
            <button onClick={() => detachProject.mutate(channel.id)} aria-label={t("channels.detachProject")}>
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ) : pickingProject ? (
          <Select
            className="h-7 w-48 text-xs"
            autoFocus
            onChange={(e) => {
              if (e.target.value) attachProject.mutate({ channelId: channel.id, projectId: e.target.value });
              setPickingProject(false);
            }}
            onBlur={() => setPickingProject(false)}
          >
            <option value="">{t("channels.selectProject")}</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
        ) : (
          <Button variant="outline" size="sm" className="h-6 gap-1 text-xs" onClick={() => setPickingProject(true)}>
            <Plus className="h-3 w-3" />
            {t("channels.attachProject")}
          </Button>
        )}
        {tabs && <div className="ml-auto shrink-0">{tabs}</div>}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {channel.members.map((m) =>
          m.is_human ? (
            <Badge key={m.id} variant="outline" className="gap-1">
              <User className="h-3 w-3" />
              {channel.created_by ?? "Marcelo"}
              <span className="text-[10px] text-muted-foreground">({t("channels.chief")})</span>
            </Badge>
          ) : (
            <div key={m.id} className="relative">
              <Badge variant="outline" className="gap-1 pr-1">
                {m.agent_id === channel.orchestrator_agent_id ? (
                  <Crown className="h-3 w-3 text-amber-500" aria-label={t("channels.orchestrator")} />
                ) : (
                  <Bot className="h-3 w-3" />
                )}
                {/* Opens this agent's own 1:1 session in the right column
                    -- the same ChatPane component Workspace/Conversas
                    uses, just agent-locked (see AgentDetailPopover above
                    for role/skills instead of a full conversation). */}
                <button
                  onClick={() => {
                    const found = agents.find((a) => a.id === m.agent_id);
                    if (found && m.agent_id) onOpenAgentSession({ id: m.agent_id, name: found.name });
                  }}
                  className="hover:underline"
                >
                  {agents.find((a) => a.id === m.agent_id)?.name ?? m.agent_id}
                </button>
                {/* Function + description + skills at a glance (2026-08-06,
                    Marcelo: "seria bom criar um icone de detalhe de cada
                    agente informando sua função e suas skills"). */}
                <button
                  onClick={() => setDetailMemberId(detailMemberId === m.id ? null : m.id)}
                  aria-label={t("channels.agentDetail")}
                  title={t("channels.agentDetail")}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <Info className="h-3 w-3" />
                </button>
                {/* This agent's function *in this channel* (2026-08-05, see
                    docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md)
                    -- always editable by Marcelo, the only human here. */}
                <Select
                  className="h-5 w-auto border-none bg-transparent px-1 py-0 text-[10px]"
                  value={m.role ?? ""}
                  onChange={(e) => updateMember.mutate({ memberId: m.id, role: e.target.value || null })}
                >
                  <option value="">{t("channels.noRole")}</option>
                  {PROJECT_AGENT_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role.replace(/_/g, " ")}
                    </option>
                  ))}
                </Select>
                {/* Purely informational designation -- see
                    ChatChannel.orchestrator_agent_id docstring. Deciding
                    proposed tasks on this agent's behalf still requires a
                    separate AuthorityDelegation grant via Governance. */}
                {m.agent_id !== channel.orchestrator_agent_id && (
                  <button
                    onClick={() =>
                      updateChannel.mutate({ channelId: channel.id, orchestrator_agent_id: m.agent_id })
                    }
                    aria-label={t("channels.chooseOrchestrator")}
                    title={t("channels.chooseOrchestrator")}
                    className="text-muted-foreground hover:text-amber-500"
                  >
                    <Crown className="h-3 w-3" />
                  </button>
                )}
                <button onClick={() => removeMember.mutate(m.id)} aria-label={t("channels.removeMember")}>
                  <X className="h-3 w-3" />
                </button>
              </Badge>
              {detailMemberId === m.id && (
                <AgentDetailPopover
                  agent={agents.find((a) => a.id === m.agent_id)}
                  member={m}
                  projectId={channel.project_id ?? undefined}
                  onClose={() => setDetailMemberId(null)}
                />
              )}
            </div>
          )
        )}
        {pickingAgent ? (
          <Select
            className="h-6 w-40 text-xs"
            autoFocus
            onChange={(e) => {
              if (e.target.value) addMember.mutate(e.target.value);
              setPickingAgent(false);
            }}
            onBlur={() => setPickingAgent(false)}
          >
            <option value="">{t("channels.selectAgent")}</option>
            {addableAgents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        ) : (
          <button
            onClick={() => setPickingAgent(true)}
            className="rounded-full border border-dashed border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent"
          >
            <Plus className="mr-0.5 inline h-3 w-3" />
            {t("channels.addMember")}
          </button>
        )}
      </div>
    </div>
  );
}

/** Floating card with an agent's function (channel + project role),
 * description and granted skills -- opened from the info icon on their
 * badge in ChannelHeader (2026-08-06). Hand-rolled positioning (no Popover
 * primitive exists in this codebase yet -- see Select/Tabs above, which
 * are hand-rolled the same way) rather than pulling in a new dependency
 * for one info card. */
function AgentDetailPopover({
  agent,
  member,
  projectId,
  onClose,
}: {
  agent?: Agent;
  member: ChatChannelMember;
  projectId?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("workspace");
  const { data: projectMemberships = [] } = useProjectMemberships(projectId);
  const projectRole = projectMemberships.find((m) => m.agent_id === agent?.id)?.role;
  const { data: agentSkills = [], isLoading: skillsLoading } = useAgentSkills(agent?.id);
  const { data: catalog = [] } = useSkills();
  const skillsById = useMemo(() => new Map(catalog.map((s) => [s.id, s])), [catalog]);

  if (!agent) return null;

  return (
    <div className="absolute left-0 top-full z-50 mt-1 w-72 rounded-md border border-border bg-card p-3 text-xs text-card-foreground shadow-lg">
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className="font-medium">{agent.name}</span>
        <button onClick={onClose} aria-label={t("common:close")}>
          <X className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </div>
      <dl className="space-y-1">
        <div>
          <dt className="text-muted-foreground">{t("channels.channelRole")}</dt>
          <dd>{member.role?.replace(/_/g, " ") || t("channels.noRole")}</dd>
        </div>
        {projectId && (
          <div>
            <dt className="text-muted-foreground">{t("channels.projectRole")}</dt>
            <dd>{projectRole?.replace(/_/g, " ") || t("channels.noRole")}</dd>
          </div>
        )}
        {agent.description && (
          <div>
            <dt className="text-muted-foreground">{t("channels.description")}</dt>
            <dd className="line-clamp-3">{agent.description}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted-foreground">{t("channels.skills")}</dt>
          {skillsLoading ? (
            <dd className="text-muted-foreground">…</dd>
          ) : agentSkills.length === 0 ? (
            <dd className="text-muted-foreground">{t("channels.noSkills")}</dd>
          ) : (
            <dd className="max-h-32 space-y-0.5 overflow-y-auto">
              {agentSkills.map((grant) => {
                const skill = skillsById.get(grant.skill_id);
                if (!skill) return null;
                return (
                  <div key={grant.id} className="flex items-center justify-between gap-2">
                    <span>{skill.name}</span>
                    <span className={cn("text-[10px]", skill.is_approved ? "text-muted-foreground" : "text-amber-500")}>
                      v{skill.version}{!skill.is_approved && ` · ${t("channels.notApproved")}`}
                    </span>
                  </div>
                );
              })}
            </dd>
          )}
        </div>
      </dl>
    </div>
  );
}

function MessageBubble({ message, agent, channelId }: { message: ChatChannelMessage; agent?: Agent; channelId: string }) {
  const { t } = useTranslation("workspace");
  const dispatch = useDispatchChannelMessage(channelId);
  const [dispatching, setDispatching] = useState(false);

  const label =
    message.author_type === "human"
      ? message.author_label ?? "Marcelo"
      : message.author_type === "system"
        ? t("channels.system")
        : agent?.name ?? message.author_label ?? t("channels.agent");

  return (
    <div className="mb-3 flex gap-2">
      <div
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-medium",
          message.author_type === "human"
            ? "bg-primary/15 text-primary"
            : message.author_type === "system"
              ? "bg-muted text-muted-foreground"
              : "bg-secondary text-secondary-foreground"
        )}
      >
        {message.author_type === "human" ? <User className="h-3.5 w-3.5" /> : message.author_type === "agent" ? <Bot className="h-3.5 w-3.5" /> : "!"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-medium">{label}</span>
          <span className="text-[10px] text-muted-foreground">{new Date(message.created_at).toLocaleTimeString()}</span>
        </div>
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        {message.author_type === "agent" && !message.triggered_demand_id && agent && (
          <button
            className="mt-1 text-[11px] text-muted-foreground underline hover:text-foreground disabled:opacity-50"
            disabled={dispatching}
            onClick={async () => {
              setDispatching(true);
              try {
                await dispatch.mutateAsync({ messageId: message.id, agentId: agent.id });
              } finally {
                setDispatching(false);
              }
            }}
          >
            {dispatching ? t("channels.dispatching") : t("channels.dispatchTask")}
          </button>
        )}
        {message.triggered_demand_id && (
          <span className="mt-1 inline-block text-[11px] text-muted-foreground">
            {t("channels.dispatched")}
          </span>
        )}
      </div>
    </div>
  );
}

function ChannelTasksPanel({
  channelId,
  channel,
  agents,
}: {
  channelId: string;
  channel: NonNullable<ReturnType<typeof useChannel>["data"]>;
  agents: Agent[];
}) {
  const { t } = useTranslation("workspace");
  const { data: tasks = [] } = useChannelTasks(channelId);
  const createTask = useCreateChannelTask(channelId);
  const updateTask = useUpdateChannelTask(channelId);
  const promoteTask = usePromoteChannelTask(channelId);
  const approveApproval = useApproveApproval();
  const rejectApproval = useRejectApproval();
  const [title, setTitle] = useState("");

  async function handleAdd() {
    if (!title.trim()) return;
    await createTask.mutateAsync({ title: title.trim() });
    setTitle("");
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          placeholder={t("channels.newTaskPlaceholder")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <Button size="sm" onClick={handleAdd} disabled={!title.trim() || createTask.isPending}>
          {t("channels.addTask")}
        </Button>
      </div>
      {tasks.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {t("channels.noTasks")}
        </p>
      )}
      <div className="space-y-1.5">
        {tasks.map((task) => {
          const isPending = task.approval_status === "pending";
          return (
            <div key={task.id} className={cn("rounded-md border px-2.5 py-1.5", isPending ? "border-amber-400/60 bg-amber-500/5" : "border-border")}>
              <div className="flex items-center gap-2">
                <Select
                  className="h-7 w-24 text-xs"
                  value={task.status}
                  disabled={isPending}
                  onChange={(e) => updateTask.mutate({ taskId: task.id, status: e.target.value })}
                >
                  <option value="todo">{t("channels.taskTodo")}</option>
                  <option value="doing">{t("channels.taskDoing")}</option>
                  <option value="done">{t("channels.taskDone")}</option>
                </Select>
                <span className="flex-1 truncate text-sm">{task.title}</span>
                {task.role_required && (
                  <Badge variant="outline" className="text-[10px]">
                    {task.role_required.replace(/_/g, " ")}
                  </Badge>
                )}
                {task.assignee_agent_id && (
                  <Badge variant="outline" className="text-[10px]">
                    {agents.find((a) => a.id === task.assignee_agent_id)?.name ?? "?"}
                  </Badge>
                )}
                {task.project_task_id ? (
                  <Badge variant="secondary" className="text-[10px]">
                    {t("channels.promoted")}
                  </Badge>
                ) : (
                  !isPending &&
                  channel.project_id && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-[11px]"
                      disabled={promoteTask.isPending}
                      onClick={() => promoteTask.mutate(task.id)}
                    >
                      {t("channels.promote")}
                    </Button>
                  )
                )}
              </div>
              {isPending && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2 border-t border-amber-400/40 pt-1.5 text-xs">
                  <span className="text-amber-700 dark:text-amber-400">
                    {t("channels.pendingApproval", {
                      agent: agents.find((a) => a.id === task.created_by_agent_id)?.name ?? "?",
                    })}
                  </span>
                  <Button
                    size="sm"
                    className="h-6 text-[11px]"
                    disabled={approveApproval.isPending}
                    onClick={() => task.approval_id && approveApproval.mutate({ id: task.approval_id, decided_by: "Marcelo" })}
                  >
                    {t("channels.approve")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px]"
                    disabled={rejectApproval.isPending}
                    onClick={() => task.approval_id && rejectApproval.mutate({ id: task.approval_id, decided_by: "Marcelo" })}
                  >
                    {t("channels.reject")}
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
