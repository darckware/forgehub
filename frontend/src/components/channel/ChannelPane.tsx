import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Crown,
  Eraser,
  Hash,
  Info,
  Loader2,
  Mic,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Sparkles,
  Square,
  Trash2,
  User,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
  FinishedStepsTrail,
  formatThinkingDuration,
  MentionFilePicker,
  QueueStepsList,
  SlashCommandPicker,
} from "@/components/chat/ChatPane";
import { ComposerShell } from "@/components/chat/ComposerShell";
import { ImprovePromptDialog } from "@/components/chat/ImprovePromptDialog";
import { AgentAvatar } from "@/components/AgentAvatar";
import { useAuthStore } from "@/store/authStore";
import { useChatSessions } from "@/hooks/useChat";
import { useChannelRoomViewModel } from "@/hooks/useChannelRoomViewModel";
import { useChannelHeaderViewModel } from "@/hooks/useChannelHeaderViewModel";
import { useProjects } from "@/hooks/useProject";
import { PROJECT_AGENT_ROLES, useProjectMemberships } from "@/hooks/useOrchestration";
import { useApproveApproval, useRejectApproval } from "@/hooks/useGovernance";
import {
  useChannel,
  useChannelMessages,
  useChannelTasks,
  useChannels,
  useCreateChannel,
  useCreateChannelTask,
  useDispatchChannelMessage,
  usePromoteChannelTask,
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
// Composer auto-grow ceiling -- matches ChatPane.tsx's own constant (kept
// as a separate copy since ChannelPane.tsx and ChatPane.tsx are two
// different files, not a shared module -- see the composer auto-grow
// effect in ChannelRoom below).
const COMPOSER_MAX_HEIGHT_PX = 240;
const SELECTED_CHANNEL_STORAGE_KEY = "forgehub-workspace-selected-channel";

export function ChannelPane({ agents, defaultProjectId }: { agents: Agent[]; defaultProjectId?: string }) {
  const { t } = useTranslation("workspace");
  const { data: channels = [] } = useChannels();
  const [selectedChannelId, setSelectedChannelId] = useState<string | undefined>(
    () => localStorage.getItem(SELECTED_CHANNEL_STORAGE_KEY) || undefined
  );
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
  useEffect(() => {
    if (selectedChannelId) localStorage.setItem(SELECTED_CHANNEL_STORAGE_KEY, selectedChannelId);
    else localStorage.removeItem(SELECTED_CHANNEL_STORAGE_KEY);
  }, [selectedChannelId]);
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
  const projectChannelId = channels.find((channel) => channel.project_id === defaultProjectId)?.id;
  const validSelectedChannelId = channels.some((channel) => channel.id === selectedChannelId) ? selectedChannelId : undefined;
  const activeChannelId = projectChannelId ?? validSelectedChannelId ?? channels[0]?.id;

  useEffect(() => {
    if (!channels.length) return;
    if (projectChannelId && projectChannelId !== selectedChannelId) {
      setSelectedChannelId(projectChannelId);
    } else if (!validSelectedChannelId && channels[0]?.id) {
      setSelectedChannelId(channels[0].id);
    }
  }, [channels, projectChannelId, selectedChannelId, validSelectedChannelId]);

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

/** Live "mm:ss" ticker for one agent's chip in the "working" strip --
 * same formatting ChatPane.tsx's own LiveThinkingLabel uses
 * (formatThinkingDuration, exported from there for this), not reused
 * as-is since the chip here is a <span> inside a <button> rather than a
 * standalone <p> (2026-08-06, "detalhamento de cada agente"). */
function AgentWorkingTicker({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000));
  return <span className="text-[10px] text-muted-foreground">{formatThinkingDuration(elapsed)}</span>;
}

/** View for the channel transcript + composer -- all state and behavior
 * live in useChannelRoomViewModel (2026-08-07, Wave 1 of
 * docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md, Marcelo: "faça
 * o item 1"). This component only renders that ViewModel's fields. */
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
  const {
    channel,
    allMessages,
    agentById,
    finishedStepsByMessageId,
    activeTab,
    setActiveTab,
    content,
    setContent,
    sending,
    canStop,
    stopping,
    stopRunningTurns,
    sendError,
    setSendError,
    runningAgents,
    activeTurn,
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
    isTranscribing,
    handleToggleRecording,
    improveOpen,
    setImproveOpen,
    improvePrompt,
  } = useChannelRoomViewModel(channelId, agents, t("channels.attachmentReadError"));

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrolledChannelRef = useRef<string | null>(null);
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    if (!allMessages) return;
    const isInitial = scrolledChannelRef.current !== channelId;
    if (isInitial) {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
      scrolledChannelRef.current = channelId;
      isNearBottomRef.current = true;
    } else if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [allMessages, runningAgents, activeTurn, channelId]);

  // Auto-grow the composer with its content, same as ChatPane's own
  // composer -- the channel's used to stay a fixed single-line box no
  // matter how long the message got, clipping/scrolling the text inside a
  // tiny box instead of growing to fit it (2026-08-07, Marcelo: "melhore
  // pois não consigo ler o texto no prompt"). The single-line height is
  // the floor (never shrinks below it), growing up to
  // COMPOSER_MAX_HEIGHT_PX before scrolling internally.
  useEffect(() => {
    const el = composerTextareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`;
  }, [content, composerTextareaRef]);

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
          <div
            ref={messagesContainerRef}
            onScroll={() => {
              const el = messagesContainerRef.current;
              if (!el) return;
              const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
              isNearBottomRef.current = distance < 80;
            }}
            className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
          >
            {allMessages.map((m) => (
              <div key={m.id}>
                {m.author_type === "agent" && (
                  <FinishedStepsTrail steps={finishedStepsByMessageId.get(m.id) ?? []} />
                )}
                <MessageBubble
                  message={m}
                  agent={
                    m.author_agent_id
                      ? agentById.get(m.author_agent_id)
                      : agents.find(
                          (a) =>
                            a.name.toLowerCase() === (m.author_label ?? "").toLowerCase() ||
                            (a.profile_slug && a.profile_slug.toLowerCase() === (m.author_label ?? "").toLowerCase())
                        )
                  }
                  channelId={channelId}
                  dispatchAgents={agents.filter((candidate) => channel.members.some((member) => member.agent_id === candidate.id && !member.muted))}
                />
              </div>
            ))}
            {allMessages.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("channels.noMessages")}
              </p>
            )}
            {/* Turno observado do servidor: aparece só quando este cliente NÃO
                é quem transmite (o bloco `sending` abaixo cobre esse caso).
                É o que se vê depois de um F5 ou de um travamento -- os
                agentes seguem trabalhando e a tela volta a acompanhar. */}
            {!sending && activeTurn && (
              <div className="flex flex-col gap-1.5 py-2">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Bot className="h-3 w-3 shrink-0 animate-pulse text-primary" />
                  {t("channels.reattachedTurn")}
                </div>
                {/* Um turno de canal roda vários agentes ao mesmo tempo, e
                    cada passo diz de quem é -- agrupar por agente é o que
                    impede os rastros de se misturarem numa lista só. */}
                {Object.entries(
                  activeTurn.steps.reduce<Record<string, typeof activeTurn.steps>>((acc, step) => {
                    const key = step.agent_id ?? "—";
                    (acc[key] ??= []).push(step);
                    return acc;
                  }, {})
                ).map(([agentId, steps]) => (
                  <div key={agentId} className="max-w-lg text-xs text-muted-foreground">
                    <span className="font-medium">
                      {agents.find((a) => a.id === agentId)?.name ?? t("channels.agent")}
                    </span>
                    <ul className="ml-4 list-disc">
                      {steps.map((step) => (
                        <li key={step.id}>{step.label ?? step.name}</li>
                      ))}
                    </ul>
                  </div>
                ))}
                {Object.entries(activeTurn.live_text_by_agent).map(([agentId, text]) => (
                  <div key={agentId} className="max-w-lg rounded-lg border border-border/60 bg-muted/20 p-2">
                    <p className="mb-1 text-xs font-medium text-muted-foreground">
                      {agents.find((a) => a.id === agentId)?.name ?? t("channels.agent")}
                    </p>
                    <p className="whitespace-pre-wrap text-sm text-foreground">{text}</p>
                  </div>
                ))}
              </div>
            )}
            {sending && (
              runningAgents.size > 0 ? (
                <div className="flex flex-col gap-1.5 py-2">
                  <p className="text-xs text-muted-foreground">
                    {t("channels.workingParallel", { count: runningAgents.size })}
                  </p>
                  <div className="flex flex-col gap-1">
                    {Array.from(runningAgents.entries()).map(([agentId, info]) => (
                      <div key={agentId} className="max-w-lg">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => setExpandedAgentId((cur) => (cur === agentId ? null : agentId))}
                            title={t("channels.agentDetail")}
                            className="flex items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs hover:bg-accent"
                          >
                            {info.steps.length > 0 &&
                              (expandedAgentId === agentId ? (
                                <ChevronDown className="h-3 w-3 shrink-0" />
                              ) : (
                                <ChevronRight className="h-3 w-3 shrink-0" />
                              ))}
                            <Bot className="h-3 w-3 shrink-0 animate-pulse text-primary" />
                            <span className="font-medium">{info.name}</span>
                            <AgentWorkingTicker startedAt={info.startedAt} />
                          </button>
                          <button
                            type="button"
                            onClick={() => onOpenAgentSession({ id: agentId, name: info.name })}
                            aria-label={t("channels.openAgentSession", { name: info.name })}
                            title={t("channels.openAgentSession", { name: info.name })}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <User className="h-3 w-3" />
                          </button>
                        </div>
                        {expandedAgentId === agentId && info.steps.length > 0 && (
                          <div className="ml-5 mt-1 space-y-1 rounded-lg border border-border/60 bg-muted/20 p-2">
                            <QueueStepsList steps={info.steps} />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {t("channels.working")}
                </div>
              )
            )}
            <div ref={messagesEndRef} />
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
              textareaClassName="min-h-0 overflow-y-auto"
              textareaStyle={{ maxHeight: COMPOSER_MAX_HEIGHT_PX }}
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
                <>
                  {/* Orchestrator-assisted prompt rewrite (2026-08-06,
                      Marcelo: "preciso que adicione ao lado esquerdo do
                      icone de microfone um icone de melhoria do prompt
                      escrito... o próprio orquestrador me ajude a criar o
                      texto"). Requires an orchestrator to be set on this
                      channel -- see ImprovePromptDialog / the backend
                      route's docstring for the precondition. */}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 self-center rounded-full"
                    aria-label={t("channels.improvePrompt")}
                    title={
                      channel.orchestrator_agent_id
                        ? t("channels.improvePrompt")
                        : t("channels.improvePromptNoOrchestrator")
                    }
                    onClick={() => setImproveOpen(true)}
                    disabled={!channel.orchestrator_agent_id}
                  >
                    <Sparkles className="h-4 w-4" />
                  </Button>
                  <Button
                    variant={isRecording ? "destructive" : "ghost"}
                    size="icon"
                    className="h-8 w-8 shrink-0 self-center rounded-full"
                    aria-label={isRecording ? t("chat:composer.stopRecording") : t("chat:composer.recordVoiceMessage")}
                    title={isRecording ? t("chat:composer.stopRecording") : t("chat:composer.recordVoiceMessage")}
                    onClick={handleToggleRecording}
                    disabled={isTranscribing}
                  >
                    {isTranscribing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : isRecording ? (
                      <Square className="h-4 w-4" />
                    ) : (
                      <Mic className="h-4 w-4" />
                    )}
                  </Button>
                  {sending && (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin self-center text-muted-foreground" />
                  )}
                  {canStop && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 self-center rounded-full text-destructive hover:text-destructive"
                      aria-label={t("channels.stopTurn")}
                      title={t("channels.stopTurn")}
                      onClick={() => void stopRunningTurns()}
                      disabled={stopping}
                    >
                      {stopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                    </Button>
                  )}
                </>
              }
            />
          </div>
          {improveOpen && (
            <ImprovePromptDialog
              initialDraft={content}
              subject={t("channels.improvePromptSubject")}
              agents={agents}
              includeLocalSlashCommands={false}
              includeHermesSlashCommands={false}
              improvePrompt={improvePrompt}
              onApply={(improved) => {
                setContent(improved);
                setImproveOpen(false);
                composerTextareaRef.current?.focus();
              }}
              onClose={() => setImproveOpen(false)}
            />
          )}
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
  const {
    projects,
    attachProject,
    detachProject,
    addMember,
    removeMember,
    updateMember,
    updateChannel,
    deleteChannel,
    clearMessages,
    pickingProject,
    setPickingProject,
    pickingAgent,
    setPickingAgent,
    detailMemberId,
    setDetailMemberId,
    editingName,
    setEditingName,
    nameDraft,
    setNameDraft,
    confirmingDelete,
    setConfirmingDelete,
    confirmingClear,
    setConfirmingClear,
    membersCollapsed,
    setMembersCollapsed,
    project,
    addableAgents,
    startEditingName,
    commitNameEdit,
    handleDeleteChannel,
    handleClearChat,
  } = useChannelHeaderViewModel(channel, agents);

  if (!channel) return null;

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
              onClick={() => setMembersCollapsed((v) => !v)}
              aria-label={membersCollapsed ? t("channels.showMembers") : t("channels.hideMembers")}
              title={membersCollapsed ? t("channels.showMembers") : t("channels.hideMembers")}
              className="text-muted-foreground hover:text-foreground"
            >
              {membersCollapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
            </button>
            {membersCollapsed && (
              <button
                type="button"
                onClick={() => setMembersCollapsed(false)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                {t("channels.memberCount", { count: channel.members.length })}
              </button>
            )}
            <button
              onClick={startEditingName}
              aria-label={t("channels.renameChannel")}
              title={t("channels.renameChannel")}
              className="text-muted-foreground hover:text-foreground"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setConfirmingDelete(true)}
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
          <InlineComboBox
            className="h-7 w-48 text-xs"
            placeholder={t("channels.selectProject")}
            options={projects.map((p) => ({ value: p.id, label: p.name }))}
            onSelect={(value) => {
              attachProject.mutate({ channelId: channel.id, projectId: value });
              setPickingProject(false);
            }}
            onClose={() => setPickingProject(false)}
          />
        ) : (
          <Button variant="outline" size="sm" className="h-6 gap-1 text-xs" onClick={() => setPickingProject(true)}>
            <Plus className="h-3 w-3" />
            {t("channels.attachProject")}
          </Button>
        )}
        <button
          onClick={() => setConfirmingClear(true)}
          aria-label={t("channels.clearChat")}
          title={t("channels.clearChat")}
          className="text-muted-foreground hover:text-destructive"
        >
          <Eraser className="h-3.5 w-3.5" />
        </button>
        {tabs && <div className="ml-auto shrink-0">{tabs}</div>}
      </div>
      {!membersCollapsed && (
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
          <InlineComboBox
            className="h-6 w-40 text-xs"
            placeholder={t("channels.selectAgent")}
            options={addableAgents.map((a) => ({ value: a.id, label: a.name }))}
            onSelect={(value) => {
              addMember.mutate(value);
              setPickingAgent(false);
            }}
            onClose={() => setPickingAgent(false)}
          />
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
      )}
      <ConfirmDialog
        open={confirmingDelete}
        title={t("channels.deleteChannel")}
        description={t("channels.confirmDelete", { name: channel.name })}
        confirmLabel={t("channels.deleteChannel")}
        loading={deleteChannel.isPending}
        onConfirm={() => handleDeleteChannel(onDeleted)}
        onCancel={() => setConfirmingDelete(false)}
      />
      <ConfirmDialog
        open={confirmingClear}
        title={t("channels.clearChat")}
        description={t("channels.confirmClearChat")}
        confirmLabel={t("channels.clearChat")}
        loading={clearMessages.isPending}
        onConfirm={handleClearChat}
        onCancel={() => setConfirmingClear(false)}
      />
    </div>
  );
}

/** Hand-rolled dropdown replacing the native <select> for the two inline
 * pickers above (project attach, add member) -- 2026-08-06, after the
 * shared Select component's appearance-none + custom-chevron fix (see
 * ui/select.tsx and index.css's .select-chevron) still left the closed
 * box illegible on Marcelo's browser ("não consigo ler o texto dentro do
 * campo dropdown", reported again after that fix shipped). Rather than
 * keep chasing a native-widget rendering quirk we can't reproduce or
 * inspect directly, this sidesteps native <select>/<option> painting
 * entirely: trigger and options are both plain buttons styled with our
 * own theme classes, so there is no OS/browser chrome left to fight. */
function InlineComboBox({
  options,
  placeholder,
  onSelect,
  onClose,
  className,
}: {
  options: { value: string; label: string }[];
  placeholder: string;
  onSelect: (value: string) => void;
  onClose: () => void;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) onClose();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onMouseDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div className="flex h-full w-full items-center justify-between rounded-md border border-input bg-background px-2 text-muted-foreground">
        {placeholder}
        <ChevronDown className="h-3.5 w-3.5 shrink-0" />
      </div>
      <div className="absolute left-0 top-full z-50 mt-1 max-h-56 w-full min-w-[10rem] overflow-y-auto rounded-md border border-border bg-card p-1 shadow-lg">
        {options.length === 0 ? (
          <p className="px-2 py-1 text-muted-foreground">{placeholder}</p>
        ) : (
          options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className="block w-full truncate rounded-sm px-2 py-1 text-left text-foreground hover:bg-accent"
              onClick={() => onSelect(opt.value)}
            >
              {opt.label}
            </button>
          ))
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

function MessageBubble({ message, agent, channelId, dispatchAgents }: { message: ChatChannelMessage; agent?: Agent; channelId: string; dispatchAgents: Agent[] }) {
  const { t } = useTranslation("workspace");
  const { user } = useAuthStore();
  const dispatch = useDispatchChannelMessage(channelId);
  const [dispatching, setDispatching] = useState(false);
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [dispatchTargetId, setDispatchTargetId] = useState(agent?.id ?? "");

  const isHuman = message.author_type === "human";
  const isAgent = message.author_type === "agent";
  const label =
    isHuman
      ? message.author_label ?? user?.username ?? "Marcelo"
      : message.author_type === "system"
        ? t("channels.system")
        : agent?.name ?? message.author_label ?? t("channels.agent");

  const avatarUrl = isHuman
    ? user?.avatar_data_url
    : isAgent
      ? agent?.avatar_data_url
      : null;

  return (
    <div className="mb-3 flex gap-2.5">
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-full text-[11px] font-medium border border-border/60 shadow-sm",
          isHuman
            ? "bg-primary/15 text-primary"
            : message.author_type === "system"
              ? "bg-muted text-muted-foreground"
              : "bg-secondary text-secondary-foreground"
        )}
      >
        {avatarUrl ? (
          <img src={avatarUrl} alt={label} className="h-full w-full object-cover" />
        ) : isHuman ? (
          <User className="h-4 w-4" />
        ) : isAgent ? (
          <AgentAvatar name={label} avatarDataUrl={agent?.avatar_data_url} size="sm" className="h-7 w-7 text-[10px]" />
        ) : (
          "!"
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-semibold text-foreground">{label}</span>
          <span className="text-[10px] text-muted-foreground">{new Date(message.created_at).toLocaleTimeString()}</span>
        </div>
        <p className="whitespace-pre-wrap text-sm mt-0.5">{message.content}</p>
        {message.author_type === "agent" && !message.triggered_demand_id && agent && (
          <div className="mt-1">
            {!dispatchOpen ? (
              <button className="text-[11px] text-muted-foreground underline hover:text-foreground" onClick={() => setDispatchOpen(true)}>
                {t("channels.dispatchTask")}
              </button>
            ) : (
              <div className="flex flex-wrap items-center gap-1.5">
                <Select className="h-7 w-40 text-xs" aria-label={t("channels.dispatchTarget")} value={dispatchTargetId} onChange={(event) => setDispatchTargetId(event.target.value)}>
                  {dispatchAgents.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
                </Select>
                <Button size="sm" className="h-7 text-xs" disabled={dispatching || !dispatchTargetId} onClick={async () => {
                  setDispatching(true);
                  try {
                    await dispatch.mutateAsync({ messageId: message.id, agentId: dispatchTargetId });
                    setDispatchOpen(false);
                  } finally {
                    setDispatching(false);
                  }
                }}>{dispatching ? t("channels.dispatching") : t("channels.confirmDispatch")}</Button>
                <Button variant="ghost" size="sm" className="h-7 text-xs" disabled={dispatching} onClick={() => setDispatchOpen(false)}>{t("channels.cancel")}</Button>
              </div>
            )}
          </div>
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
  const [assigneeAgentId, setAssigneeAgentId] = useState("");

  async function handleAdd() {
    if (!title.trim()) return;
    await createTask.mutateAsync({ title: title.trim(), assignee_agent_id: assigneeAgentId || undefined });
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
        <Select className="w-44" aria-label={t("channels.taskAssignee")} value={assigneeAgentId} onChange={(event) => setAssigneeAgentId(event.target.value)}>
          <option value="">{t("channels.unassigned")}</option>
          {channel.members.filter((member) => member.agent_id && !member.muted).map((member) => {
            const candidate = agents.find((agent) => agent.id === member.agent_id);
            return candidate ? <option key={candidate.id} value={candidate.id}>{candidate.name}</option> : null;
          })}
        </Select>
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
