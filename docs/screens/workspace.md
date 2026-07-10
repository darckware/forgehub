# Screen: Workspace

## Route & Purpose

- Route: `/workspace` (registered in `frontend/src/App.tsx:31`, label "Workspace" in `frontend/src/components/layout/Sidebar.tsx:49`).
- Component: `frontend/src/pages/workspace/index.tsx` (`WorkspacePage`, default export).
- Purpose: a single tabbed surface combining (a) chat with Hermes Foundation agents that have a `profile_slug`, and (b) real terminal sessions on the host (plain bash, or a CLI/runtime launcher such as Claude, Codex, Antigravity, Hermes), so a user can plan/converse with an agent and drop into a live shell against the same checkout without leaving the page. It is the renamed/evolved former "chat" page (`git status` shows `frontend/src/pages/chat/index.tsx` → `frontend/src/pages/workspace/index.tsx`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/workspace/index.tsx` | Page shell: toolbar, tab strip (drag-to-reorder, close), tab persistence, renders one `ChatTabPanel` or `TerminalPane` per open tab. |
| `frontend/src/pages/workspace/index.tsx` (`ChatTabPanel`, local) | Full chat UI for one chat tab: session sidebar, message list, composer (text/file/voice). Stays mounted (CSS `hidden`) while inactive so drafts/scroll position survive tab switches. |
| `frontend/src/pages/workspace/index.tsx` (`AgentPickerButton`, local) | Icon button + dropdown to pick the chat agent when the history sidebar is collapsed. |
| `frontend/src/pages/workspace/index.tsx` (`ChatItemMenu`, local) | Per-session "..." menu: rename / pin-unpin / delete. |
| `frontend/src/pages/workspace/index.tsx` (`AgentSelectorPill`, local) | Pill inside the composer bar to switch the tab's agent. |
| `frontend/src/pages/workspace/index.tsx` (`AttachMenuButton`, local) | "+" menu in the composer; today exposes only "Enviar arquivo" (pick a file to attach). |
| `frontend/src/pages/workspace/index.tsx` (`MessageBubble`, local) | Renders one chat message (markdown content, attachment name, timestamp). |
| `frontend/src/components/TerminalPane.tsx` | xterm.js terminal bound over a WebSocket to a host tmux session; one instance per terminal tab. |
| `frontend/src/components/WorkingDirPicker.tsx` | Pill + popover folder browser used to set the working directory applied to newly-opened terminal tabs. |
| `frontend/src/components/Markdown.tsx` | Shared markdown renderer (react-markdown + remark-gfm) used for assistant/user message content. |
| `frontend/src/components/ui/button.tsx`, `textarea.tsx` | shadcn/ui primitives used throughout. |

## Data & API Calls

| Data shown | Source hook | Backend/host-bridge endpoint | Method |
|---|---|---|---|
| Agents eligible for chat (filtered to `profile_slug` truthy) | `useAgents()` (`frontend/src/hooks/useAgent.ts`) | `/api/v1/agents` | GET |
| Chat sessions list (per agent, for the history sidebar) | `useChatSessions(agentId)` (`frontend/src/hooks/useChat.ts`) | `/api/v1/chat/sessions?agent_id=` | GET |
| Messages of the active session | `useChatMessages(sessionId)` | `/api/v1/chat/sessions/{session_id}/messages` | GET |
| New chat session | `useCreateChatSession()` | `/api/v1/chat/sessions` | POST |
| Rename / pin / unpin session | `useUpdateChatSession(agentId)` | `/api/v1/chat/sessions/{session_id}` | PATCH |
| Delete session | `useDeleteChatSession(agentId)` | `/api/v1/chat/sessions/{session_id}` | DELETE |
| Send message (text and/or file) | `useSendChatMessage(agentId)` | `/api/v1/chat/sessions/{session_id}/messages` (multipart form) | POST |
| Voice-to-text transcription | `useTranscribeAudio()` | `/api/v1/chat/transcribe` (multipart form) | POST |
| Working-directory folder listing | `useBrowseDirs(path, enabled)` (`frontend/src/hooks/useTerminalBrowse.ts`) | `/api/v1/terminal/browse-dirs` | GET |
| Terminal session output/input (xterm.js stream) | n/a (raw `WebSocket` opened directly in `TerminalPane.tsx`) | `/api/v1/terminal/ws?session=&command=&cwd=` | WS |
| Pasted-image upload inside a terminal pane | n/a (raw `fetch` in `TerminalPane.tsx`) | `/api/v1/terminal/upload-image` (multipart form) | POST |
| Kill a terminal's backing tmux session (on tab close) | n/a (raw `apiClient.post` in `index.tsx:748`) | `/api/v1/terminal/sessions/{session_id}/kill` | POST |

Backend routes are thin proxies: `backend/app/api/routes/chat.py` persists `chat_sessions`/`chat_messages` and forwards the actual message to the host-bridge (`POST host-bridge:/v1/chat` or `/v1/chat-with-image`), which shells out to `hermes chat -p <profile>`. `backend/app/api/routes/terminal.py` is a pure byte-pipe proxy (HTTP for browse/kill/upload, WebSocket relay for the terminal stream) to `host-bridge/app.py`'s `/v1/browse-dirs`, `/v1/terminal/sessions/{id}/kill`, `/v1/terminal/upload-image`, and `/v1/terminal/ws`. The host-bridge is the only process with access to the host's `hermes`/tmux/PTY — see its module docstring (`host-bridge/app.py:1`).

## Actions Available

- **New Chat** (toolbar button) — opens a new chat tab for the currently-active tab's agent (or the first chatable agent if none active).
- **New Terminal** (toolbar button) — opens a new plain-bash terminal tab (`openTerminalTab("bash")`).
- **CLI launcher icons** (Claude / Codex / Antigravity) — open a terminal tab that auto-types the corresponding CLI command (`claude`, `codex`, `agy`) once the tmux session is created.
- **Runtime launcher icon** (Hermes) — same mechanism, types `hermes`.
- **Working-directory picker** — browse host folders and select one; applied as `cwd` to terminal tabs opened afterward (does not retroactively affect already-open tabs).
- **Toggle chat history sidebar** (PanelLeftClose/Open icon) — collapses/expands the session list for the active chat tab only; replaced in the toolbar by an `AgentPickerButton` when collapsed.
- **Tab strip**: click to switch active tab; drag-and-drop to reorder; "x" to close a tab (closing a terminal tab calls the kill endpoint; closing a chat tab does not delete the chat session, only the tab).
- **Per-chat-session "..." menu**: Rename (inline edit, commits on blur/Enter, cancels on Escape), Pin/Unpin (re-sorts list, pinned first), Delete.
- **Composer**: type message, Enter to send (Shift+Enter for newline); "+" → "Enviar arquivo" to attach a file (image previews inline, other files show a paperclip chip, removable via "x"); paste an image directly into the textarea to attach it; mic button to record audio (toggles recording, transcribes on stop and appends the result to the composer text); agent-selector pill to retarget the tab to a different agent (clears the active session for that tab).
- **Terminal pane**: standard terminal keyboard/mouse interaction (mouse wheel scroll enabled via tmux `mouse on`); pasting an image uploads it and types its host file path into the shell.

## States

- **Empty (no chatable agents)**: page renders a centered message — "No agents with a Hermes profile are available to chat with yet." (`index.tsx:787-796`) — no tabs/toolbar shown at all.
- **Empty (no tabs open)**: centered placeholder — "No tabs open / Start a chat or open a terminal using the buttons above." (`index.tsx:959-967`). On first visit (no persisted tabs, no pending chat-handoff draft), a default chat tab is auto-opened instead of showing this state (`index.tsx:767-777`).
- **Empty (chat with no messages yet)**: "Send a message to start the conversation with {agent}." (`index.tsx:578-582`).
- **Empty (no sessions for an agent)**: "No chats yet." in the history sidebar (`index.tsx:569-571`).
- **Loading (working-dir folder browse)**: spinner + "Loading…" inside the popover (`WorkingDirPicker.tsx:85-90`).
- **Loading (send message in flight)**: animated three-dot "typing" bubble while `sendMessage.isPending` (`index.tsx:598-606`); the just-sent user message is optimistically rendered via local `pendingMessage` state before the server round-trip resolves.
- **Loading (transcription in flight)**: mic button shows a spinner and is disabled (`index.tsx:650-659`).
- **Error (send message failed)**: inline red text "Failed to send message: {error}" below the message list (`index.tsx:607-611`).
- **Error (folder browse failed)**: "Failed to list directory." in the picker popover (`WorkingDirPicker.tsx:91`).
- **No explicit UI state** for: terminal WebSocket connect/disconnect/error (silently retries are not implemented — see Notes), chat-session create/update/delete mutation failures (no error UI), transcription failure (no error UI), image-upload-on-paste failure in a terminal (silently swallowed via `.catch(() => {})`).

## Business Rules Surfaced Here

None directly enforced here against `docs/BUSINESS_RULES.md` — that document's numbered rules cover the core domain entities (Product, Pipeline, Planning, Execution, Agent/Skill, Task, Governance). The Workspace screen's backing tables (`chat_sessions`, `chat_messages`, defined in `backend/app/db/models/chat.py`) and the terminal/tmux session concept are not part of that domain model; they are a separate "ops/chat bridge" surface. The only rule-like behavior visibly enforced in this screen's own code:

- A chat session can only target an agent that has a Hermes profile (`profile_slug` set) — enforced both client-side (`chatableAgents` filter, `index.tsx:669-672`) and server-side (`_get_chattable_agent_or_404`, `backend/app/api/routes/chat.py:41-50`, 400 if the agent lacks a profile).
- A message must have non-empty text or a file (`backend/app/api/routes/chat.py:182-183`, 400 otherwise) — not separately enforced in the frontend (Send is disabled client-side under the same condition, `index.tsx:430`).

## Dependencies

- **Backend domain `agent`** (`backend/app/api/routes/agent.py`, `db/models/agent.py`) — supplies the agent list and `profile_slug`/`name` used to populate chatable agents and tab labels.
- **Backend `chat` module** (`backend/app/api/routes/chat.py`, `db/models/chat.py`, `api/schemas/chat.py`) — owns `chat_sessions`/`chat_messages` persistence; not a documented core "domain" per CLAUDE.md's domain-module list (`product`, `project`, `pipeline`, `backlog`, `task`, `agent`, `artifact`, `governance`), but follows the same `db/models` + `api/schemas` + `api/routes` layering.
- **Backend `terminal` module** (`backend/app/api/routes/terminal.py`) — stateless proxy, no DB access at all.
- **host-bridge service** (`host-bridge/app.py`, runs on the host, not in Docker) — actually drives `hermes chat`, `faster-whisper` transcription, and host tmux/PTY sessions; required for every chat send, transcription, and terminal action on this screen. Authenticated to the backend via a shared `X-Bridge-Token`/`FORGEHUB_BRIDGE_TOKEN` secret.
- **`frontend/src/store/chatHandoff.ts`** (Zustand, not persisted) — one-shot relay consumed on mount to pre-fill a new chat tab's composer when navigating here from another page's "send to chat" action (e.g. Crons/Scripts pages per its docstring).
- **Browser APIs**: `localStorage` (tab/active-tab persistence), `MediaRecorder`/`getUserMedia` (voice recording), `WebSocket` (terminal stream), `ResizeObserver` (terminal refit).

## Notes / Improvement Opportunities

- Tab state (`tabs`, `activeTabId`) is persisted to `localStorage` under fixed keys `forgehub-workspace-tabs`/`forgehub-workspace-active-tab` (`index.tsx:53-54`) with no schema versioning — a future shape change to `WorkspaceTab` would silently misrender or crash on `JSON.parse` of stale stored data rather than migrating it. The `try { … } catch { return [] }` guard (`index.tsx:676-680`) only protects against parse errors, not shape drift.
- Terminal WebSocket has no reconnect/backoff logic and no visible "disconnected" state in `TerminalPane.tsx` — if the WS drops (e.g. backend restart), the pane just stops updating with no user-facing indication; the user has to close and reopen the tab.
- Closing a terminal tab's "kill" call is fire-and-forget (`index.tsx:748`, `.catch(() => {})`) — a failed kill leaves an orphaned tmux session on the host with no feedback to the user or retry path.
- `AttachMenuButton`'s single menu item is hardcoded in Portuguese ("Enviar arquivo", `index.tsx:286`), while most of the rest of the UI strings are in English (e.g. "New Chat", "No chats yet.") — inconsistent i18n; likely leftover from earlier copy.
- The composer placeholder ("Peça ao {agent}", `index.tsx:638`) is also Portuguese, same inconsistency.
- No error UI exists for `useCreateChatSession`, `useUpdateChatSession`, `useDeleteChatSession`, or `useTranscribeAudio` mutation failures — only `useSendChatMessage` renders an inline error (`index.tsx:607-611`). A failed rename/pin/delete/transcription fails silently from the user's perspective.
- `handleToggleRecording` (`index.tsx:483-507`) calls `navigator.mediaDevices.getUserMedia` with no try/catch — if the user denies microphone permission or no input device exists, the promise rejects unhandled (visible only as a console error / unhandled rejection, no UI feedback, `isRecording` likely stays stuck `false` without the recorder ever starting).
- Switching a chat tab's agent via `AgentSelectorPill` silently clears `sessionId` (`useEffect` at `index.tsx:365-367`) with no confirmation — if the user was mid-conversation and accidentally taps a different agent in the pill, the visible session resets to "no chat selected" for that tab (the original session is not deleted, just deselected, but this isn't surfaced to the user).
- `TerminalPane.tsx:69-72` strips an xterm.js DECRQM parser-crashing escape sequence via regex as a workaround for an upstream `@xterm/xterm` 6.0.0 bug; this is a targeted patch rather than a library upgrade/fix and should be revisited when xterm.js ships a fix.
- The component file `frontend/src/pages/workspace/index.tsx` is ~970 lines covering five local sub-components plus the page itself; could be split into separate files (e.g. `ChatTabPanel.tsx`, `AgentPickerButton.tsx`) consistent with the rest of the codebase's per-file component convention, though no functional issue today.
