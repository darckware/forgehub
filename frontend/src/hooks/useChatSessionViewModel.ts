import { useEffect, useMemo, useRef, useState } from "react";
import { useProjects } from "@/hooks/useProject";
import {
  useChatGroups,
  useChatSessions,
  useCreateChatGroup,
  useCreateChatSession,
  useDeleteChatGroup,
  useDeleteChatSession,
  useSearchChatSessions,
  useUpdateChatGroup,
  useUpdateChatSession,
  type ChatSession,
} from "@/hooks/useChat";

/** ViewModel Hook for ChatPane.tsx's session sidebar -- the first slice of
 * Wave 1's `ChatPane.tsx` split in `docs/architecture/
 * FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` (2026-08-07, Marcelo: "continua a
 * migração para o ChatPane.tsx"). Owns which session is active plus the
 * full session list: search, the Project/Group sidebar tree, rename, pin,
 * move, bulk-clear, and creating new sessions/groups.
 *
 * Deliberately does NOT own: the composer/draft, the message-send queue,
 * or voice-conversation state -- those are separate, not-yet-extracted
 * concerns (see the plan's remaining ChatPane.tsx sub-items) that all read
 * `sessionId` from this hook rather than owning their own copy of it. In
 * particular `ensureSession` is exposed here (it only needs
 * `sessionId`/`setSessionId`/`createSession`, all already owned by this
 * hook) so the still-unextracted priming effect and voice/queue code can
 * call it without duplicating session-bootstrap logic. */
export function useChatSessionViewModel(
  agentId: string,
  startNewSession: boolean | undefined,
  initialSessionId?: string,
  onSessionChange?: (sessionId: string) => void,
) {
  const [sessionId, setSessionId] = useState<string>(initialSessionId ?? "");
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const { data: sessions } = useChatSessions(agentId || undefined);

  // Debounced search across session titles + message content (see
  // search_chat_sessions in chat.py) -- 300ms so we're not hitting the DB
  // on every keystroke.
  const [chatSearchInput, setChatSearchInput] = useState("");
  const [chatSearchTerm, setChatSearchTerm] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setChatSearchTerm(chatSearchInput), 300);
    return () => clearTimeout(t);
  }, [chatSearchInput]);
  const { data: chatSearchResults, isFetching: isSearchingChats } = useSearchChatSessions(
    chatSearchTerm,
    agentId || undefined
  );
  const displayedSessions = chatSearchTerm.trim() ? chatSearchResults ?? [] : sessions ?? [];

  // Sidebar tree (2026-07-28): a session's placement is exclusive --
  // Project (working_directory_path) XOR Group (group_id) XOR neither
  // (loose list, the only thing the sidebar showed before this). See
  // ChatSession.group_id's backend docstring for the exclusivity rule.
  const { data: chatProjects } = useProjects();
  const { data: chatGroups } = useChatGroups();
  const createChatGroup = useCreateChatGroup();
  const updateChatGroup = useUpdateChatGroup();
  const deleteChatGroup = useDeleteChatGroup();

  const projectsWithPath = useMemo(
    () =>
      (chatProjects ?? []).filter(
        (p): p is typeof p & { working_directory_path: string } => Boolean(p.working_directory_path)
      ),
    [chatProjects]
  );
  const sessionsByProjectPath = useMemo(() => {
    const map = new Map<string, ChatSession[]>();
    for (const s of displayedSessions) {
      if (!s.working_directory_path) continue;
      map.set(s.working_directory_path, [...(map.get(s.working_directory_path) ?? []), s]);
    }
    return map;
  }, [displayedSessions]);
  const sessionsByGroupId = useMemo(() => {
    const map = new Map<string, ChatSession[]>();
    for (const s of displayedSessions) {
      if (!s.group_id) continue;
      map.set(s.group_id, [...(map.get(s.group_id) ?? []), s]);
    }
    return map;
  }, [displayedSessions]);
  const looseSessions = useMemo(
    () => displayedSessions.filter((s) => !s.working_directory_path && !s.group_id),
    [displayedSessions]
  );
  const projectFoldersWithSessions = useMemo(
    () => projectsWithPath.filter((p) => (sessionsByProjectPath.get(p.working_directory_path) ?? []).length > 0),
    [projectsWithPath, sessionsByProjectPath]
  );

  const [projectsRootOpen, setProjectsRootOpen] = useState(true);
  const [groupsRootOpen, setGroupsRootOpen] = useState(true);
  const [openProjectPaths, setOpenProjectPaths] = useState<Set<string>>(new Set());
  const [openGroupIds, setOpenGroupIds] = useState<Set<string>>(new Set());
  function toggleOpenPath(set: Set<string>, key: string): Set<string> {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  }
  const [newGroupNameRoot, setNewGroupNameRoot] = useState("");
  const [creatingGroup, setCreatingGroup] = useState(false);

  const createSession = useCreateChatSession();
  const deleteSession = useDeleteChatSession(agentId || undefined);
  const updateSession = useUpdateChatSession(agentId || undefined);

  // Shared session bootstrap: the priming effect and handleSend (both
  // still in ChatPane.tsx) can genuinely race on a fresh pane (priming
  // fires on mount; a fast paste+send lands right after) -- sharing one
  // in-flight promise guarantees they land in the SAME session instead of
  // the context going to one and the user's message to another.
  const sessionPromiseRef = useRef<Promise<string> | null>(null);
  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    if (!sessionPromiseRef.current) {
      sessionPromiseRef.current = createSession
        .mutateAsync({ agent_id: agentId })
        .then((created) => {
          setSessionId(created.id);
          return created.id;
        })
        .catch((err) => {
          sessionPromiseRef.current = null;
          throw err;
        });
    }
    return sessionPromiseRef.current;
  }

  const previousAgentIdRef = useRef(agentId);
  useEffect(() => {
    if (previousAgentIdRef.current === agentId) return;
    previousAgentIdRef.current = agentId;
    setSessionId("");
    sessionPromiseRef.current = null;
  }, [agentId]);

  const onSessionChangeRef = useRef(onSessionChange);
  useEffect(() => {
    onSessionChangeRef.current = onSessionChange;
  }, [onSessionChange]);
  useEffect(() => {
    onSessionChangeRef.current?.(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (startNewSession) return;
    if (!sessions) return;
    if (sessionId && sessions.some((session) => session.id === sessionId)) return;
    setSessionId(sessions[0]?.id ?? "");
  }, [sessionId, sessions, startNewSession]);

  function handleStartRename(s: ChatSession) {
    setEditingSessionId(s.id);
    setEditingTitle(s.title);
  }

  function handleCommitRename() {
    if (!editingSessionId) return;
    const title = editingTitle.trim();
    if (title) {
      updateSession.mutate({ sessionId: editingSessionId, title });
    }
    setEditingSessionId(null);
  }

  function handleTogglePin(s: ChatSession) {
    updateSession.mutate({ sessionId: s.id, pinned: !s.pinned });
  }

  const activeSession = sessions?.find((s) => s.id === sessionId);

  function handleSetSessionWorkingDirectory(path: string | null) {
    if (!sessionId) return;
    updateSession.mutate({ sessionId, working_directory_path: path });
  }

  // Per-row moves from ChatItemMenu -- unlike handleSetSessionWorkingDirectory
  // above (header picker, active session only), these work on any session
  // in the tree, not just the one currently open.
  function handleMoveSessionToProject(targetSessionId: string, path: string | null) {
    updateSession.mutate({ sessionId: targetSessionId, working_directory_path: path });
  }
  function handleMoveSessionToGroup(targetSessionId: string, groupId: string | null) {
    updateSession.mutate({ sessionId: targetSessionId, group_id: groupId });
  }
  function handleCreateGroupAndMoveSession(targetSessionId: string, name: string) {
    createChatGroup.mutate(name, {
      onSuccess: (group) => {
        updateSession.mutate({ sessionId: targetSessionId, group_id: group.id });
      },
    });
  }

  // Bulk "limpeza" (2026-07-28): hard-deletes every session in the given
  // scope -- Project folder, Group folder, or the loose list ("geral", no
  // project/group) -- each cleared independently from its own icon, never
  // bundled. Confirms once for the whole batch, not per session, via the
  // shared in-app ConfirmDialog (2026-07-29) rather than window.confirm --
  // consistent with the rest of the app's destructive-action pattern (see
  // InboxGroupTree.tsx) and not a native browser popup.
  const [pendingClearSessions, setPendingClearSessions] = useState<{
    sessions: ChatSession[];
    message: string;
  } | null>(null);

  function handleClearSessions(sessionsToClear: ChatSession[], confirmMessage: string) {
    if (sessionsToClear.length === 0) return;
    setPendingClearSessions({ sessions: sessionsToClear, message: confirmMessage });
  }

  function confirmClearSessions() {
    if (!pendingClearSessions) return;
    for (const s of pendingClearSessions.sessions) {
      deleteSession.mutate(s.id, {
        onSuccess: () => {
          if (s.id === sessionId) setSessionId("");
        },
      });
    }
    setPendingClearSessions(null);
  }

  function handleNewChat() {
    if (!agentId) return;
    createSession.mutate({ agent_id: agentId }, { onSuccess: (session) => setSessionId(session.id) });
  }

  return {
    sessionId,
    setSessionId,
    ensureSession,
    editingSessionId,
    setEditingSessionId,
    editingTitle,
    setEditingTitle,
    sessions,
    chatSearchInput,
    setChatSearchInput,
    chatSearchTerm,
    isSearchingChats,
    displayedSessions,
    chatGroups,
    createChatGroup,
    updateChatGroup,
    deleteChatGroup,
    projectsWithPath,
    sessionsByProjectPath,
    sessionsByGroupId,
    looseSessions,
    projectFoldersWithSessions,
    projectsRootOpen,
    setProjectsRootOpen,
    groupsRootOpen,
    setGroupsRootOpen,
    openProjectPaths,
    setOpenProjectPaths,
    openGroupIds,
    setOpenGroupIds,
    toggleOpenPath,
    newGroupNameRoot,
    setNewGroupNameRoot,
    creatingGroup,
    setCreatingGroup,
    createSession,
    deleteSession,
    handleStartRename,
    handleCommitRename,
    handleTogglePin,
    activeSession,
    handleSetSessionWorkingDirectory,
    handleMoveSessionToProject,
    handleMoveSessionToGroup,
    handleCreateGroupAndMoveSession,
    pendingClearSessions,
    setPendingClearSessions,
    handleClearSessions,
    confirmClearSessions,
    handleNewChat,
  };
}
