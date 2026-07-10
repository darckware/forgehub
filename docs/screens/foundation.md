# Screen: Foundation

## Route & Purpose

`/foundation` — registered in `frontend/src/App.tsx:55`, component `FoundationPage` (`frontend/src/pages/foundation/index.tsx`). Sidebar entry: "Foundation" / `Landmark` icon, `frontend/src/components/layout/Sidebar.tsx:71`.

Purpose: a read-write **browser and editor for the Hermes Foundation rule/governance markdown tree** (`/root/.hermes/foundation` on the host), the actual rule set the Hermes agents operate under (`governance/`, `policies/`, `docs/`, `agents/`, `map/`, `vault/`, `continuity/`, ...). The screen offers three views of the same tree: a file browser + markdown reader/editor ("Note"), an Obsidian-style force-directed `[[wikilink]]` graph of the whole tree ("Graph"), and a per-document heading-outline mind map ("Mind map"). It is **not** one of ForgeHub's 8 DB-backed domains — no row in the `company` Postgres schema is read or written by this screen.

**Important correction to the task framing**: this screen does *not* use `backend/app/api/routes/foundation.py` (the router described in `CLAUDE.md` as reading `/vault/Agents` and `/profiles` for agent SOUL/sub-agents/skills/MEMORY). It uses a different, sibling router, `backend/app/api/routes/foundation_docs.py` (prefix `/api/v1/foundation-docs`), mounted read-write at `/foundation-root` ← host `/root/.hermes/foundation` (`docker-compose.yml:39`). `foundation.py`'s `/vault/Agents` + `/profiles` data (agent SOUL.md/MEMORY.md/skills/sub-agents) is instead consumed elsewhere in the app — by `frontend/src/pages/agent/ProfileFilesCard.tsx` via `frontend/src/hooks/useFoundation.ts`, on the **Agents** screen, not this one. See `docs/screens/agents.md` for that surface. (The two routers/hooks share the word "foundation" in their names, which is the likely source of the mix-up in this task's brief.) `frontend/src/hooks/useFoundationCrons.ts` and `useFoundationScripts.ts` (which front `foundation.py`'s `/crons` and `/scripts` endpoints) are also unrelated to this screen — they back the separate Crons screen (`frontend/src/pages/crons/`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/foundation/index.tsx` | Page shell: left sidebar doc tree, right pane with Note/Mind map/Graph view switch, edit/save/delete controls for the selected document. |
| `frontend/src/components/DocTree.tsx` | Recursive collapsible file-tree renderer (folders default-expanded only at depth 0); clicking a file calls `onSelectFile(path)`. |
| `frontend/src/components/Markdown.tsx` | Read-only markdown renderer (`react-markdown` + `remark-gfm`) used for the "Note" view when not editing. |
| `frontend/src/components/GraphView.tsx` | Force-directed 2D graph (via the `force-graph` canvas library) of all notes as nodes and `[[wikilink]]` references as edges; clicking a node calls back into the page to switch to Note view on that doc. |
| `frontend/src/components/MindMapView.tsx` | Renders the selected document's heading outline (headings only, fenced code blocks stripped) as a collapsible/zoomable radial tree via `markmap-lib`/`markmap-view`, with a `markmap-toolbar` overlay. |
| `frontend/src/components/ui/textarea.tsx` (shadcn primitive) | Raw markdown editor surface while `isEditing` is true. |
| `frontend/src/hooks/useFoundationDocs.ts` | Zod schema + TanStack Query hooks (`useFoundationTree`, `useFoundationDoc`, `useFoundationGraph`, `useUpdateFoundationDoc`, `useDeleteFoundationDoc`) — the actual data layer for this screen. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| File/folder tree of the Foundation markdown root | `useFoundationTree()` | `/api/v1/foundation-docs/tree` | GET |
| Selected document's raw markdown content | `useFoundationDoc(path)` | `/api/v1/foundation-docs/doc?path=...` | GET |
| Whole-tree `[[wikilink]]` graph (nodes + edges) | `useFoundationGraph()` | `/api/v1/foundation-docs/graph` | GET |
| Save edited document content | `useUpdateFoundationDoc()` | `/api/v1/foundation-docs/doc?path=...` | PUT |
| Delete a document | `useDeleteFoundationDoc()` | `/api/v1/foundation-docs/doc?path=...` | DELETE |

All requests go through `frontend/src/lib/api.ts`'s `apiClient`, per project convention. `useFoundationDoc` is only `enabled` when a path is selected (`useFoundationDocs.ts:42`).

## Actions Available

- **Select a document** — clicking a file node in the tree (`DocTree`) sets `selectedPath` and switches `viewMode` to `"note"` if currently on Graph view via node click (`index.tsx:48-51`), or stays on whatever view is active for a sidebar click. Switching `selectedPath` always resets `isEditing` to `false` (`index.tsx:31-33`).
- **Switch view mode** — three-way toggle button group: Note / Mind map / Graph (`index.tsx:84-112`). "Mind map" is disabled until a document is selected (`index.tsx:98`).
- **Edit** (`index.tsx:117-120`) — only shown in Note view with a document loaded; seeds the textarea draft from the loaded content and enters edit mode.
- **Save** (`index.tsx:142-150`) — calls `PUT /api/v1/foundation-docs/doc` with the draft content; on success exits edit mode. Button shows a spinner while `updateDoc.isPending`.
- **Cancel edit** (`index.tsx:138-141`) — discards the draft, exits edit mode without saving.
- **Delete** (`index.tsx:121-135`) — guarded by a native `window.confirm` (`index.tsx:55`); calls `DELETE /api/v1/foundation-docs/doc` and clears `selectedPath` on success.
- **Click a graph node** (`GraphView` → `handleSelectFromGraph`, `index.tsx:48-51`) — jumps to that document in Note view.
- **Mind map toolbar** (zoom/pan/fit, rendered by `markmap-toolbar`) — pure client-side interaction with the rendered SVG, no API call.

There is no "create new document" action anywhere in the UI or backend — per the backend module docstring, `foundation_docs.py` supports "editing and deleting existing files only," no file creation.

## States

- **Tree loading**: spinner + "Loading Foundation…" in the sidebar (`index.tsx:64-69`).
- **Tree error**: destructive text "Failed to load Foundation docs." (`index.tsx:70`) — this fires in particular when `/foundation-root` isn't mounted, since `GET /tree` raises `404 "Foundation directory is not mounted"` if `FOUNDATION_ROOT.is_dir()` is false (`foundation_docs.py:49-51`). Confirms the CLAUDE.md note that this whole router 404s/returns empty outside the Docker container (or without the equivalent local bind mount).
- **Tree empty**: italic "No markdown docs found." when the tree array is loaded and empty (`index.tsx:72-74`).
- **No document selected (Note view)**: italic prompt "Select a document to read the Hermes rules." (`index.tsx:158-160`).
- **Document loading**: inline spinner + "Loading document…" (`index.tsx:161-166`).
- **Save error**: inline destructive text showing the thrown error's `message` (`index.tsx:167-171`).
- **Delete error**: inline destructive text showing the thrown error's `message` (`index.tsx:172-176`).
- **Graph loading**: spinner + "Building graph…" (`index.tsx:190-195`).
- **Graph view, no explicit empty state**: if `graph` resolves with zero nodes, `GraphView` just renders an empty canvas — no "no docs" message in this branch.
- **Mind map, no document selected**: italic "Select a document first." (`index.tsx:202`).
- **No "not found" state for a deleted-out-from-under-you doc**: if `selectedPath` still points at a doc removed by a concurrent process, `useFoundationDoc` will surface a 404 through React Query's error channel, but `index.tsx` only checks `docLoading`, never `isError`, for the doc query — so a doc-fetch error renders nothing (no error banner), unlike the tree/save/delete cases. See Notes.

## Business Rules Surfaced Here

None — this is a filesystem-backed Hermes Foundation governance-doc viewer/editor, outside ForgeHub's core DB domain model (no Product/Project/Pipeline/Backlog/Task/Agent/Artifact/Governance table is read or written here). The only "rule" enforced is a backend path-traversal/extension guard (`foundation_docs.py:38-44`, `_resolve_doc_path`): every read/write/delete must resolve to an existing `.md` file inside `/foundation-root`, and `resolve_doc_path` (`backend/app/core/markdown_docs.py:53-58`) rejects any path that escapes that root.

## Dependencies

- **Host filesystem mount**: `/root/.hermes/foundation` on the Docker host → `/foundation-root` inside `forgehub-backend`, **read-write** (`docker-compose.yml:39`, comment at `docker-compose.yml:35-38`). This is the sole dependency for this screen's tree/doc/graph/save/delete endpoints.
- Not used by this screen, despite superficially similar naming/contents: `/root/.hermes/foundation/vault/Agents` (mounted as `/vault`, read-write, for the **Obsidian vault** screen via `vault.py`) and `/root/.hermes/profiles` (mounted as `/profiles`, for `foundation.py`'s agent SOUL/MEMORY/skills/sub-agents, consumed by the **Agents** screen's `ProfileFilesCard`). Also unrelated to this screen: `/root/.hermes/foundation/agents` → `/foundation-agents` (ro) — read by `backend/app/core/hermes_sync.py` (`FOUNDATION_AGENTS_DIR`), which backs the **Agents** screen's "Sync from Hermes Foundation" action, not this one. `/root/.hermes/foundation/governance` → `/governance` (ro) is mounted but, per a search of `backend/app/api/routes/` and `backend/app/core/`, **not read by any code** at the time of writing (see Notes) — likely redundant since `/foundation-root` already covers `/root/.hermes/foundation/governance` by walking the full tree.
- Shares its tree-walk/graph-build implementation with the Obsidian vault screen via `backend/app/core/markdown_docs.py` (`build_tree`, `build_graph`, `resolve_doc_path`) — code is shared, but the data (root directory) is not.

## Notes / Improvement Opportunities

- **Task-brief / CLAUDE.md mismatch**: the docstring in `backend/app/api/routes/foundation.py` (and the corresponding paragraph in `CLAUDE.md`) describes `/vault/Agents` + `/profiles`-backed agent metadata (SOUL.md, sub-agents, skills, MEMORY.md). That router is real and does back a screen — but not this one. The `/foundation` route's actual backend is `foundation_docs.py` / `/foundation-root`. Anyone relying on the CLAUDE.md description to understand `/foundation` would be looking at the wrong router and the wrong filesystem mount; worth a doc fix upstream (CLAUDE.md or a router rename) if this is going to keep confusing future readers.
- **Doc-fetch error not surfaced**: `index.tsx:21` destructures `isLoading` from `useFoundationDoc` but never `isError`/`error`; if the GET `/doc` call fails (e.g., 404 because the file was deleted by another process, or a 400 from an invalid path), the Note pane shows nothing — no spinner, no error text, no document. Contrast with the tree query, which does show a destructive message on `isError` (`index.tsx:70`).
- **No "document not found" path through the UI**: since `DocTree` only ever surfaces paths that exist in the last-loaded tree, a 404 from `GET /doc` would only happen via a race (delete-then-select) or a stale tree — low likelihood, but combined with the previous point it fails silently.
- **`window.confirm` for delete** (`index.tsx:55`) — a native browser dialog rather than an in-app confirmation modal; inconsistent with shadcn/ui being the canonical UI stack (per `CLAUDE.md`'s UI library governance section) but functional.
- **No create-document action** anywhere (UI or backend) — by design per the backend docstring ("No file creation -- editing and deleting existing files only"), but worth flagging since both the Note view's empty state and the overall screen give no indication that new docs must be created out-of-band (e.g., directly on the host filesystem or via Obsidian) and then will simply appear in the tree on next load.
- **Graph view has no empty-state message** — if the Foundation tree contains no `[[wikilink]]` edges (or no markdown files at all), `GraphView` renders a blank canvas with no explanatory text, unlike the Note and Mind map views which both have explicit "select/empty" copy.
- **`/governance` read-only mount appears unused.** `docker-compose.yml:33` mounts `/root/.hermes/foundation/governance:/governance:ro`, but no code under `backend/app/` references `/governance` as a `Path(...)` constant (verified by grep across `api/routes/` and `core/`) — this looks like either a dead/legacy mount or one provisioned ahead of an unbuilt feature. (`/foundation-agents`, mounted alongside it, *is* used — by `backend/app/core/hermes_sync.py` for the Agents screen's sync action — so it is `/governance` specifically that looks orphaned.) Not load-bearing for this screen either way, since `/foundation-root` already covers the full `/root/.hermes/foundation` tree, governance subdirectory included, by walking it recursively.
- **Mind map reduces to headings-only** (`MindMapView.tsx:12-30`) by design (documented rationale: avoids 150+ node graphs from deeply nested lists) — this means list-only documents with no `#`/`##` headings will render an effectively empty mind map; no fallback or warning for that case.
