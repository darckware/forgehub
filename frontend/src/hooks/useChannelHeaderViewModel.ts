import { useEffect, useState } from "react";
import type { Agent } from "@/hooks/useAgent";
import { useProjects } from "@/hooks/useProject";
import {
  useAddChannelMember,
  useAttachChannelProject,
  useChannel,
  useClearChannelMessages,
  useDeleteChannel,
  useDetachChannelProject,
  useRemoveChannelMember,
  useUpdateChannel,
  useUpdateChannelMember,
} from "@/hooks/useChannel";

/** ViewModel Hook for ChannelHeader -- the third ChannelPane.tsx sub-item
 * of Wave 1 in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`
 * (2026-08-07, Marcelo: "vai pelo ChannelHeader"), following
 * `useChannelRoomViewModel.ts`'s pilot the same session. Covers rename,
 * delete/clear confirmation, member add/remove/role, and project
 * attach/detach -- a separate screen region from ChannelRoom's own
 * composer/send state, with no state shared between the two.
 *
 * i18n strings stay in the View, same as the other ViewModel hooks in
 * this app -- none of this hook's own logic needs a translated string
 * (unlike useChannelRoomViewModel's one attachment-error message), only
 * the View's JSX does (aria-labels, confirm dialog copy). */
export function useChannelHeaderViewModel(channel: ReturnType<typeof useChannel>["data"], agents: Agent[]) {
  const { data: projects = [] } = useProjects();
  const attachProject = useAttachChannelProject();
  const detachProject = useDetachChannelProject();
  const addMember = useAddChannelMember(channel!.id);
  const removeMember = useRemoveChannelMember(channel!.id);
  const updateMember = useUpdateChannelMember(channel!.id);
  const updateChannel = useUpdateChannel();
  const deleteChannel = useDeleteChannel();
  const clearMessages = useClearChannelMessages();
  const [pickingProject, setPickingProject] = useState(false);
  const [pickingAgent, setPickingAgent] = useState(false);
  const [detailMemberId, setDetailMemberId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  // 2026-08-06, Marcelo: "adicione um icone do lado esquerdo do icone de
  // editar o nome no canal para ocultar/mostrar os agentes" -- collapses
  // the member-badges row, which can get tall with a full 9-member team.
  const [membersCollapsed, setMembersCollapsed] = useState(
    () => localStorage.getItem("forgehub-channel-members-collapsed") === "1"
  );
  useEffect(() => {
    localStorage.setItem("forgehub-channel-members-collapsed", membersCollapsed ? "1" : "0");
  }, [membersCollapsed]);

  const project = channel ? projects.find((p) => p.id === channel.project_id) : undefined;
  const memberAgentIds = channel
    ? new Set(channel.members.filter((m) => !m.is_human).map((m) => m.agent_id))
    : new Set<string | null>();
  const addableAgents = channel ? agents.filter((a) => !memberAgentIds.has(a.id)) : [];

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

  function handleDeleteChannel(onDeleted: () => void) {
    setConfirmingDelete(false);
    deleteChannel.mutate(channel!.id, { onSuccess: onDeleted });
  }

  function handleClearChat() {
    setConfirmingClear(false);
    clearMessages.mutate(channel!.id);
  }

  return {
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
  };
}
