# ForgeHub Key Page Dependency Trees

Local imports are traced recursively and deduplicated within each tree. Third-party packages are omitted.

## `/` — Dashboard

Entry: `frontend/src/pages/Dashboard.tsx`

- `frontend/src/pages/Dashboard.tsx`
  - `frontend/src/components/ToolVersionsCard.tsx`
    - `frontend/src/assets/icons/pi.svg`
    - `frontend/src/hooks/useToolVersions.ts`
    - `frontend/src/store/toolUpdate.ts`
  - `frontend/src/components/SystemStatsCard.tsx`
    - `frontend/src/hooks/useSystemStats.ts`
  - `frontend/src/components/RemoteAccessCard.tsx`
    - `frontend/src/hooks/useRemoteAccess.ts`
  - `frontend/src/components/ProjectsForgeRouterCard.tsx`
    - `frontend/src/hooks/useProject.ts`
    - `frontend/src/hooks/useAgent.ts`
    - `frontend/src/hooks/useAppConfig.ts`
    - `frontend/src/hooks/useProjectForgeRouter.ts`
  - `frontend/src/components/CronsCard.tsx`
    - `frontend/src/hooks/useFoundationCrons.ts`
    - `frontend/src/hooks/usePermission.ts`
      - `frontend/src/store/authStore.ts`
  - `frontend/src/components/ui/{badge,button,card,tabs}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/agent-activity` — Agent Activity

Entry: `frontend/src/pages/agent-activity/index.tsx`

- `frontend/src/pages/agent-activity/index.tsx`
  - `frontend/src/components/AgentActivityStage.tsx`
  - `frontend/src/components/AgentActivityTasksDialog.tsx`
  - `frontend/src/hooks/useAgentActivityViewModel.ts`
    - `frontend/src/hooks/useAgent.ts`
    - `frontend/src/hooks/useDemands.ts`
    - `frontend/src/hooks/useForgeRouterActivity.ts`
    - `frontend/src/hooks/useProject.ts`
    - `frontend/src/components/AgentInboxTree.tsx`
      - `frontend/src/components/InboxGroupTree.tsx`
      - `frontend/src/components/ui/{button,input,confirm-dialog}.tsx`
  - `frontend/src/components/ui/{badge,button,card}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/cockpit` — Product Cockpit

Entry: `frontend/src/pages/cockpit/index.tsx`

- `frontend/src/pages/cockpit/index.tsx`
  - `frontend/src/components/AgentTelemetryPanel.tsx`
    - `frontend/src/hooks/useFactory.ts`
  - `frontend/src/hooks/useProduct.ts`
  - `frontend/src/hooks/useProject.ts`
  - `frontend/src/hooks/useBacklog.ts`
  - `frontend/src/hooks/useTask.ts`
  - `frontend/src/components/ui/{card,badge,button,tabs}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/workspace` — Multi-runtime Workspace

Entry: `frontend/src/pages/workspace/index.tsx`

- `frontend/src/pages/workspace/index.tsx`
  - `frontend/src/assets/icons/pi.svg`
  - `frontend/src/components/TerminalPane.tsx`
  - `frontend/src/components/WorkingDirPicker.tsx`
  - `frontend/src/components/chat/ChatPane.tsx`
    - `frontend/src/components/chat/ComposerShell.tsx`
    - `frontend/src/components/chat/ImprovePromptDialog.tsx`
      - `frontend/src/hooks/useImprovePromptViewModel.ts`
      - `frontend/src/hooks/usePromptTechniques.ts`
    - `frontend/src/components/chat/TestApplicationDialog.tsx`
    - `frontend/src/components/Markdown.tsx`
    - `frontend/src/hooks/useActiveTurn.ts`
    - `frontend/src/hooks/useChatLanguage.ts`
    - `frontend/src/hooks/useChatSessionViewModel.ts`
  - `frontend/src/components/channel/ChannelPane.tsx`
    - `frontend/src/hooks/useChannelRoomViewModel.ts`
    - `frontend/src/hooks/useChannelHeaderViewModel.ts`
    - `frontend/src/hooks/useOrchestration.ts`
    - `frontend/src/hooks/useGovernance.ts`
  - `frontend/src/components/TelegramPane.tsx`
    - `frontend/src/hooks/useServers.ts`
  - `frontend/src/components/WebAppPane.tsx`
    - `frontend/src/components/MacroInstructionsPanel.tsx`
    - `frontend/src/components/WebAutomationPanel.tsx`
    - `frontend/src/hooks/useWorkspaceBrowser.ts`
  - `frontend/src/hooks/{useAgent,useAssistant,useChat,useClickOutside,useDemands,useProduct,useProject,useTerminalBrowse}.ts`
  - `frontend/src/pages/workspace/workspaceState.ts`
  - `frontend/src/store/assistantStore.ts`
  - `frontend/src/components/ui/{button,confirm-dialog,input,label,select,textarea}.tsx`
  - `frontend/src/lib/{api,assistantFileDrag,theme,utils}.ts`

## `/projects/:id` — Project Detail

Entry: `frontend/src/pages/project/[id].tsx`

- `frontend/src/pages/project/[id].tsx`
  - `frontend/src/components/ProjectFileBrowser.tsx`
    - `frontend/src/components/Markdown.tsx`
    - `frontend/src/hooks/useProjectFiles.ts`
  - `frontend/src/components/EntityDocsCard.tsx`
    - `frontend/src/hooks/useDocLinks.ts`
  - `frontend/src/components/mcp/ProjectMcpServerManager.tsx`
    - `frontend/src/hooks/useProjectMcp.ts`
  - `frontend/src/pages/project/ProjectForm.tsx`
    - `frontend/src/components/WorkingDirPicker.tsx`
    - `frontend/src/hooks/useProjectFormViewModel.ts`
  - `frontend/src/pages/project/{StructureNodeForm,ProjectPlanForm,ChangeRequestForm}.tsx`
  - `frontend/src/components/ProjectAutomationCard.tsx`
    - `frontend/src/hooks/useAgent.ts`
    - `frontend/src/hooks/useOrchestration.ts`
  - `frontend/src/hooks/{useBacklog,useProduct,useProject,useSystemControl,useTask}.ts`
  - `frontend/src/components/ui/{badge,button,card,confirm-dialog,input,label,select,table,textarea}.tsx`
  - `frontend/src/lib/{api,theme,utils}.ts`

## `/tasks/:id` — Task Detail and Automation

Entry: `frontend/src/pages/task/[id].tsx`

- `frontend/src/pages/task/[id].tsx`
  - `frontend/src/components/EntityDocsCard.tsx`
    - `frontend/src/hooks/useDocLinks.ts`
  - `frontend/src/components/TaskAutomationCard.tsx`
    - `frontend/src/hooks/useExecutionRuntime.ts`
    - `frontend/src/hooks/useOrchestration.ts`
  - `frontend/src/components/TaskDependenciesCard.tsx`
  - `frontend/src/hooks/{useAgent,useBacklog,useProject,useTask}.ts`
  - `frontend/src/components/ui/{badge,button,card,input,label,select,table,textarea}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/demands` — Messages and Agent Demands

Entry: `frontend/src/pages/demands/index.tsx`

- `frontend/src/pages/demands/index.tsx`
  - `frontend/src/pages/demands/DemandFormPanel.tsx`
    - `frontend/src/store/authStore.ts`
    - `frontend/src/hooks/{useAgent,useDemands,useProject,useTask}.ts`
  - `frontend/src/components/InboxGroupTree.tsx`
  - `frontend/src/components/AgentInboxTree.tsx`
  - `frontend/src/components/AgentCommsGraph.tsx`
  - `frontend/src/components/DemandsStatsPanel.tsx`
  - `frontend/src/components/DemandsControlPanel.tsx`
  - `frontend/src/components/Markdown.tsx`
  - `frontend/src/hooks/{useAgent,useAssistant,useDemands,useProject}.ts`
  - `frontend/src/components/ui/{badge,button,card,confirm-dialog,input,select,table,tabs,textarea}.tsx`
  - `frontend/src/lib/{api,theme,utils}.ts`

## `/notifications` — Operational Notifications

Entry: `frontend/src/pages/notifications/index.tsx`

- `frontend/src/pages/notifications/index.tsx`
  - `frontend/src/components/layout/NotificationBell.tsx`
    - `frontend/src/i18n/index.ts`
    - `frontend/src/hooks/useClickOutside.ts`
    - `frontend/src/hooks/useNotifications.ts`
  - `frontend/src/components/ui/{badge,button,card,confirm-dialog}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/governance` — Approvals and Policies

Entry: `frontend/src/pages/governance/index.tsx`

- `frontend/src/pages/governance/index.tsx`
  - `frontend/src/pages/governance/ApprovalForm.tsx`
    - `frontend/src/hooks/{useArtifact,useGovernance,usePipeline,useProduct,useTask}.ts`
  - `frontend/src/components/ui/{badge,button,card,input,label,select,tabs,textarea}.tsx`
  - `frontend/src/lib/{api,utils}.ts`

## `/agents` — Agent Roster and Profiles

Entry: `frontend/src/pages/agent/index.tsx`

- `frontend/src/pages/agent/index.tsx`
  - `frontend/src/components/AgentEcosystemHierarchy.tsx`
    - `frontend/src/components/AgentAvatar.tsx`
    - `frontend/src/components/AgentProfileFileChips.tsx`
      - `frontend/src/components/Markdown.tsx`
    - `frontend/src/components/AgentRosterTable.tsx`
    - `frontend/src/components/TelegramStatusBadge.tsx`
    - `frontend/src/hooks/{useAgent,useFoundationCrons,useFoundationScripts}.ts`
  - `frontend/src/components/ui/{badge,button,card,confirm-dialog,select,table}.tsx`
  - `frontend/src/lib/{api,theme,utils}.ts`
