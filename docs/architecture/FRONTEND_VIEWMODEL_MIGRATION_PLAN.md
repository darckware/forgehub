# Frontend ViewModel Hook migration — tracking plan

> Status: living checklist. **Whoever converts a screen updates its checkbox in the same
> change** (Claude/Porthus does this automatically whenever a conversion lands — 2026-08-07,
> Marcelo: "nesse controle você tem que ir baixando automaticamente quando formos fazendo as
> correções nas telas"). Don't batch-update after the fact from memory — flip the box in the
> same commit/session that does the work, so this file never drifts from reality.

## Why this exists

Marcelo asked for ForgeHub's frontend to adopt the org's canonical
`05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md` (`/root/.hermes/knowledge_base/marcelo/stack/`)
incrementally, screen by screen ("de vagar por tela"), not as a big-bang rewrite. That standard's
§21 "ViewModel Hooks" + the CRUD UX rules (§48 and Marcelo's own list: delete confirmation, a busy
state on every action button, form validation) are now documented as a standing convention in
`CLAUDE.md` under "Frontend: per-domain page + hook pairing" — this file is the *tracker* for
rolling that convention out across the existing 71 pages + the heavier shared components, not a
restatement of the convention itself (read `CLAUDE.md` for what "converted" means).

**Explicitly out of scope for this plan**: ForgeHub does not adopt the standard's Feature-Sliced
Design layers (`app/pages/widgets/features/entities/shared`) — the existing `pages/<domain>/` +
`hooks/use<Domain>.ts` pairing stays. This plan only tracks the ViewModel Hook + CRUD UX split
inside that existing structure.

## Conversion checklist (what "done" means for one screen)

- [ ] Non-trivial state/behavior (async calls, confirmation, coordination between fields) lives in
      a `use<Thing>ViewModel` hook in `frontend/src/hooks/`, not inline `useState`s in the
      component.
- [ ] The hook exposes an explicit `status` state machine (`"idle" | "loading" | "submitting" |
      "error" | ...` — only the states the screen actually has, per
      `useImprovePromptViewModel.ts`'s own docstring on right-sizing this) instead of loose
      booleans (`isLoading`/`isSaving`/`hasError` as separate fields).
- [ ] Every destructive action goes through `ConfirmDialog` — never fires straight off a click.
- [ ] Every button bound to a mutation shows `disabled={isPending}` + a spinner
      (`Loader2 animate-spin`) while in flight.
- [ ] Forms validate with React Hook Form + `zodResolver` against a schema colocated with the
      domain's `use<Domain>.ts` hook (or inline in the form if the domain hook doesn't already
      hold one).
- [ ] `tsc -b`, `npm run build`, and `npm test` all still pass; if the screen has no test file yet
      and the conversion was non-trivial, consider adding one rather than leaving the ViewModel
      hook completely unverified.

A screen already satisfying all six bullets before this plan existed doesn't need touching just to
tick a box — note it "already conformant" instead of forcing a rewrite.

## How items get picked up

Per `CLAUDE.md`: convert a screen when you're touching it anyway (new feature, bug fix) or when
its `useState` block has grown unwieldy — **not** a scheduled top-down rewrite independent of real
work. The waves below are a priority order for *when a choice exists*, not a sprint plan with
dates. Re-sequence a wave if real work lands somewhere out of order — this file should track
reality, not the other way around.

---

## Wave 0 — pilot (done)

- [x] `frontend/src/hooks/useImprovePromptViewModel.ts` + `frontend/src/components/chat/ImprovePromptDialog.tsx` (2026-08-07)

## Wave 1 — Chat & Channels (active area, highest line count, highest risk)

These two are the biggest files in the app by far and the most recently active (voice dictation,
prompt improvement, parallel sends, clear-chat all landed here in the last two weeks). Full
ViewModel extraction in one pass is unrealistic — each needs internal sub-splitting into several
`use<Concern>ViewModel` hooks (composer/draft state, streaming/queue state, session management,
voice/TTS) before/alongside the View split, not one mega-hook. Treat each bullet below as its own
sub-conversion, ticked off independently.

- [ ] `frontend/src/components/chat/ChatPane.tsx` (4412 lines) — split by concern, at least:
  - [x] session list/selection state — done 2026-08-07: `frontend/src/hooks/useChatSessionViewModel.ts`
        owns `sessionId` + the full session list (search, Project/Group sidebar tree, rename, pin,
        move, bulk-clear, `ensureSession` bootstrap). Composer/queue/voice (below) all still read
        `sessionId`/`ensureSession` from this hook rather than owning their own copy — that's why
        this one was tackled first, it's the piece everything else depends on. The still-inline
        priming effect (sends `primingMessage` as the session's opening turn) deliberately stays
        in `ChatPane.tsx` itself, not this hook: it also touches `setQueue`, which belongs to the
        not-yet-extracted send/streaming concern below.
  - [ ] composer/draft + attachment state
  - [ ] send/streaming + queue state (`ChatQueueItem` draining)
  - [ ] voice/TTS state — the largest remaining piece: SpeechRecognition + MediaRecorder/VAD
        fallback + TTS + barge-in detection, all via raw browser APIs with no test coverage here.
        Extract last, and verify by hand in the browser (mic + voice conversation), not just
        tsc/build -- this is exactly the kind of subsystem a bad extraction could silently break.
- [x] `frontend/src/components/channel/ChannelPane.tsx` (1788 lines) — split by concern:
  - [x] composer/draft state (mirrors ChatPane's) + send/streaming + per-agent `runningAgents`
        state — done together, 2026-08-07: `frontend/src/hooks/useChannelRoomViewModel.ts` +
        `ChannelRoom` (the transcript+composer half of the file) now purely renders it. Kept as
        one hook rather than two, since `handleSend` itself couples both concerns (reads
        `content`, drives `sendingCount`/`runningAgents`, clears the composer) — splitting further
        would just pass the same state back and forth between two hooks.
  - [x] channel header/membership state — done 2026-08-07:
        `frontend/src/hooks/useChannelHeaderViewModel.ts` + `ChannelHeader` now purely renders it
        (rename, delete/clear confirmation, member add/remove/role, project attach/detach). Its
        `ConfirmDialog`+`loading` usage for delete/clear was already CRUD-UX-conformant before
        this change, nothing to fix there. `ChannelPane.tsx`'s ViewModel split is now complete.

## Wave 2 — Software Factory pipeline (active area, product-facing)

- [ ] `frontend/src/pages/system-map/SystemMapCanvas.tsx` (1185 lines)
- [ ] `frontend/src/pages/backlog/index.tsx` (841 lines)
- [ ] `frontend/src/pages/conception/index.tsx` (630 lines)
- [ ] `frontend/src/pages/screen-inspector/index.tsx` (438 lines)
- [ ] `frontend/src/pages/cockpit/index.tsx` (406 lines)
- [ ] `frontend/src/pages/task/[id].tsx` (485 lines)
- [ ] `frontend/src/pages/backlog/PlanningItemForm.tsx` (372 lines)
- [ ] `frontend/src/pages/pipeline/[id].tsx` (563 lines)
- [ ] `frontend/src/pages/governance/PoliciesPage.tsx` (379 lines)
- [ ] `frontend/src/pages/task/index.tsx` (352 lines)
- [ ] `frontend/src/pages/concept-erd/index.tsx` (165 lines)
- [ ] `frontend/src/pages/version-closure/index.tsx` (175 lines)
- [ ] `frontend/src/pages/governance/index.tsx` (209 lines)
- [ ] `frontend/src/pages/governance/[id].tsx` (200 lines)
- [ ] `frontend/src/pages/governance/ApprovalForm.tsx` (211 lines)
- [ ] `frontend/src/pages/pipeline/index.tsx` (237 lines)
- [ ] `frontend/src/pages/pipeline-templates/index.tsx` (371 lines)
- [ ] `frontend/src/pages/pipeline/PipelineForm.tsx` (143 lines)
- [ ] `frontend/src/pages/task/TaskForm.tsx` (255 lines)
- [ ] `frontend/src/pages/systems-hub/index.tsx` (131 lines)
- [ ] `frontend/src/pages/system-map/index.tsx` (141 lines)
- [ ] `frontend/src/pages/project-scope/index.tsx` (40 lines)

## Wave 3 — Messages/Inbox

- [ ] `frontend/src/pages/demands/index.tsx` (1310 lines)
- [ ] `frontend/src/pages/demands/DemandFormPanel.tsx` (596 lines)
- [ ] `frontend/src/components/InboxGroupTree.tsx` (463 lines)
- [ ] `frontend/src/components/AgentInboxTree.tsx` (357 lines)
- [ ] `frontend/src/components/AgentCommsGraph.tsx` (450 lines)
- [ ] `frontend/src/components/DemandsStatsPanel.tsx` (244 lines)
- [ ] `frontend/src/components/DemandsControlPanel.tsx` (199 lines)
- [ ] `frontend/src/components/ConvertMenu.tsx` (267 lines)

## Wave 4 — Admin/Ops (large, lower change frequency)

- [ ] `frontend/src/pages/deploy/index.tsx` (2042 lines — largest page in the app)
- [ ] `frontend/src/pages/foundation/index.tsx` (919 lines)
- [ ] `frontend/src/pages/docs/index.tsx` (904 lines)
- [ ] `frontend/src/pages/database/SchemaPage.tsx` (807 lines)
- [ ] `frontend/src/pages/skills/index.tsx` (762 lines)
- [ ] `frontend/src/pages/servers/index.tsx` (672 lines)
- [ ] `frontend/src/pages/crons/index.tsx` (633 lines)
- [ ] `frontend/src/pages/auditor/index.tsx` (628 lines)
- [ ] `frontend/src/pages/system-control/index.tsx` (604 lines)
- [ ] `frontend/src/pages/obsidian/index.tsx` (571 lines)
- [ ] `frontend/src/pages/hindsight/index.tsx` (549 lines)
- [ ] `frontend/src/pages/tools/index.tsx` (536 lines)
- [ ] `frontend/src/pages/settings/index.tsx` (514 lines)
- [ ] `frontend/src/pages/database/DiagramPage.tsx` (491 lines)
- [ ] `frontend/src/pages/database/QueryPage.tsx` (345 lines — already has the Ctrl+Enter
      convention `ImprovePromptDialog` borrowed; check ViewModel/CRUD bullets only)
- [ ] `frontend/src/pages/mcp/index.tsx` (291 lines)
- [ ] `frontend/src/pages/news/index.tsx` (302 lines)
- [ ] `frontend/src/pages/prompt-commands/index.tsx` (250 lines)
- [ ] `frontend/src/pages/notifications/index.tsx` (264 lines)
- [ ] `frontend/src/pages/database/DatabaseLayout.tsx` (123 lines)
- [ ] `frontend/src/components/mcp/McpCatalogPanel.tsx` (564 lines)
- [ ] `frontend/src/components/mcp/ProjectMcpServerManager.tsx` (359 lines)
- [ ] `frontend/src/components/mcp/McpServerManager.tsx` (443 lines)
- [ ] `frontend/src/components/AgentEcosystemHierarchy.tsx` (702 lines)
- [ ] `frontend/src/components/WebAppPane.tsx` (476 lines)
- [ ] `frontend/src/components/ProjectFileBrowser.tsx` (467 lines)
- [ ] `frontend/src/components/TerminalPane.tsx` (269 lines)
- [ ] `frontend/src/components/TaskDependenciesCard.tsx` (245 lines)
- [ ] `frontend/src/components/ToolVersionsCard.tsx` (231 lines)
- [ ] `frontend/src/components/BackgroundTestsPanel.tsx` (179 lines)
- [ ] `frontend/src/components/DocTree.tsx` (347 lines)
- [ ] `frontend/src/components/DocumentBrowser.tsx` (178 lines, has a test file already)
- [ ] `frontend/src/components/DocumentWorkspace.tsx` (190 lines)
- [ ] `frontend/src/components/layout/Sidebar.tsx` (406 lines)
- [ ] `frontend/src/components/layout/UserSettingsMenu.tsx` (384 lines)
- [ ] `frontend/src/components/layout/CommandPalette.tsx` (186 lines)
- [ ] `frontend/src/components/layout/NotificationBell.tsx` (123 lines)
- [ ] `frontend/src/components/AgentTelemetryPanel.tsx` (211 lines)
- [ ] `frontend/src/components/ProjectsForgeRouterCard.tsx` (409 lines)

## Wave 5 — Simple domain CRUD (list + form pairs, already close to the pattern)

Products, projects, agents, users, profiles, artifacts — these are mostly straightforward
TanStack Query list/detail/form triads and likely need the least work per screen.

- [ ] `frontend/src/pages/product/index.tsx` (621 lines)
- [ ] `frontend/src/pages/product/ProductDetail.tsx` (255 lines)
- [ ] `frontend/src/pages/project/[id].tsx` (1049 lines)
- [ ] `frontend/src/pages/project/index.tsx` (307 lines)
- [x] `frontend/src/pages/project/ProjectForm.tsx` (241 lines) — done 2026-08-07:
      `frontend/src/hooks/useProjectFormViewModel.ts` owns the product→version cascading select,
      the current-version-lookup effect, and the backup-location slug preview; the form's own
      `react-hook-form` state (register/handleSubmit/watch/setValue/errors) is re-exported
      wholesale via `...form` rather than cherry-picked, since it's already react-hook-form's own
      Model/Controller surface, not this hook's authored logic. Delete-confirmation/spinner/Zod
      checklist items were already conformant before this change (form has no delete action;
      submit button already showed a spinner via the `isSubmitting` prop; already used
      `zodResolver`).
- [ ] `frontend/src/pages/project/ChangeRequestForm.tsx` (152 lines)
- [ ] `frontend/src/pages/project/ProjectPlanForm.tsx` (92 lines)
- [ ] `frontend/src/pages/project/StructureNodeForm.tsx` (126 lines)
- [ ] `frontend/src/pages/agent/[id].tsx` (636 lines)
- [ ] `frontend/src/pages/agent/index.tsx` (255 lines)
- [ ] `frontend/src/pages/agent/AgentProfileFilesCard.tsx` (283 lines)
- [ ] `frontend/src/pages/agent/AgentAutomationCard.tsx` (190 lines)
- [ ] `frontend/src/pages/agent/AgentMcpServersCard.tsx` (38 lines)
- [ ] `frontend/src/pages/backlog/[id].tsx` (275 lines)
- [ ] `frontend/src/pages/artifact/index.tsx` (218 lines)
- [ ] `frontend/src/pages/artifact/[id].tsx` (204 lines)
- [ ] `frontend/src/pages/artifact/ArtifactForm.tsx` (171 lines)
- [ ] `frontend/src/pages/users/index.tsx` (144 lines)
- [ ] `frontend/src/pages/users/UserForm.tsx` (210 lines)
- [ ] `frontend/src/pages/profiles/index.tsx` (105 lines)
- [ ] `frontend/src/pages/profiles/ProfileForm.tsx` (204 lines)
- [ ] `frontend/src/pages/conception/CaptureIdeaDialog.tsx` (83 lines)
- [ ] `frontend/src/pages/auth/LoginPage.tsx` (377 lines)
- [ ] `frontend/src/pages/forgerouter/index.tsx` (44 lines)
- [ ] `frontend/src/pages/Dashboard.tsx` (47 lines)
- [ ] `frontend/src/pages/database/SchemaContext.tsx` (51 lines)

---

## Progress summary

Update this table whenever a wave's checkboxes change — quick glance without counting checkboxes
by hand.

| Wave | Items | Done |
|---|---|---|
| 0 — Pilot | 1 | 1 |
| 1 — Chat & Channels | 2 (7 sub-items) | ChannelPane.tsx fully done (3/3 sub-items, 2026-08-07); ChatPane.tsx not started (0/4) |
| 2 — Software Factory | 21 | 0 |
| 3 — Messages/Inbox | 8 | 0 |
| 4 — Admin/Ops | 30 | 0 |
| 5 — Simple CRUD | 25 | 1 (ProjectForm.tsx, 2026-08-07) |
