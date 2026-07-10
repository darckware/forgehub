# Screen: Knowledge Base

## Route & Purpose

- Route: `/obsidian` (registered in `frontend/src/App.tsx:54`; path unchanged even though the sidebar label was renamed).
- Sidebar label: "Knowledge Base" (`frontend/src/components/layout/Sidebar.tsx:70`, icon `Gem`) — was previously "Obsidian"; the component file, directory (`pages/obsidian/`), route path, and hook/query-key names (`useVault*`, `vault-tree`, `vault-graph`) all still say "obsidian"/"vault".
- Component: `frontend/src/pages/obsidian/index.tsx` (`ObsidianPage`, default export).
- Purpose: a browser and editor for an external Obsidian vault (a folder of `.md` notes with `[[wikilink]]`-style cross-references), surfaced inside ForgeHub instead of requiring the desktop Obsidian app. Lets a user navigate the vault's folder/file tree, read a note as rendered markdown, edit and save it back to disk, delete a note, view the vault-wide wikilink graph, and view a single note's heading outline as a mind map.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/obsidian/index.tsx` | Page shell: file-tree sidebar, view-mode switch (Note / Mind map / Graph), per-mode toolbar actions (Edit/Save/Cancel/Delete), and the three content panes. |
| `frontend/src/components/DocTree.tsx` | Recursive collapsible file/folder tree (`DocTree`/`DocTreeItem`); folders default expanded only at depth 0; clicking a file calls `onSelectFile`. Shared with the Foundation docs screen (generic doc-tree component, not vault-specific). |
| `frontend/src/components/GraphView.tsx` | Obsidian-style force-directed graph (`GraphView`): notes as nodes, `[[wikilinks]]` as edges, rendered via the `force-graph` canvas library (2D-only, no React wrapper); clicking a node calls `onSelectNode`, which switches the page back to Note view with that note selected. |
| `frontend/src/components/MindMapView.tsx` | Renders one note's heading outline (`#`–`######`, code fences stripped) as a collapsible/zoomable radial tree via `markmap-lib`/`markmap-view`/`markmap-toolbar`; scoped to the single selected note, unlike `GraphView`'s vault-wide graph. |
| `frontend/src/components/Markdown.tsx` | Shared markdown renderer (`react-markdown` + `remark-gfm`) used to render the read-only note view. |
| `frontend/src/components/ui/button.tsx`, `textarea.tsx` | shadcn/ui primitives used throughout (toolbar buttons, edit textarea). |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Vault file/folder tree (`.md` files only) | `useVaultTree()` | `/api/v1/vault/tree` | GET |
| Selected note's raw content | `useVaultNote(path)` (enabled only once a path is selected) | `/api/v1/vault/note?path=` | GET |
| Vault-wide wikilink graph (nodes + edges) | `useVaultGraph()` | `/api/v1/vault/graph` | GET |
| Save edited note content | `useUpdateVaultNote()` | `/api/v1/vault/note?path=` | PUT |
| Delete a note | `useDeleteVaultNote()` | `/api/v1/vault/note?path=` | DELETE |

All hooks live in `frontend/src/hooks/useVault.ts` and go through the shared `apiClient` (`frontend/src/lib/api.ts`). On successful delete, the tree query and graph query are invalidated and the note query is removed from cache (`useVault.ts:67-71`); on successful update, the note's cache entry is updated in place (`useVault.ts:57-59`) — the tree/graph are not invalidated after an edit (only content changed, not structure/links).

Backend: `backend/app/api/routes/vault.py`, router prefix `/api/v1/vault`. It reads/writes directly against a bind-mounted directory (`VAULT_ROOT = Path("/vault")`, `vault.py:26`) — there is no database table backing this screen. Tree-walking and graph-building logic (`build_tree`, `build_graph`, `resolve_doc_path`) live in the shared `backend/app/core/markdown_docs.py`, reused by both this router and `api/routes/foundation_docs.py` (the separate Foundation rules browser). `resolve_doc_path` rejects any path that escapes the vault root, and `_resolve_note_path` (`vault.py:38-44`) additionally rejects any non-`.md` target — both checked before every note read/write/delete.

## Actions Available

- **Browse the tree** (left sidebar) — expand/collapse folders, click a file to select and load it.
- **Switch view mode** (Note / Mind map / Graph toggle in the content-pane toolbar) — "Mind map" is disabled when no note is selected (`index.tsx:98`); "Note" and "Graph" are always enabled.
- **Edit a note** — "Edit" button (visible in Note view when a note is loaded) switches to a plain `Textarea` pre-filled with the note's current content.
- **Save** — commits the textarea content via `PUT /api/v1/vault/note`; returns to read view on success.
- **Cancel** — discards the draft and returns to read view without saving.
- **Delete a note** — "Delete" button, gated by a native `window.confirm` ("Delete "{path}"? This removes the note file permanently.", `index.tsx:55`); on success, clears the current selection.
- **Click a node in Graph view** — selects that note and switches back to Note view (`handleSelectFromGraph`, `index.tsx:35-38`).
- **View a note's mind map** — switching to Mind map mode renders the currently selected note's heading outline as a zoomable/collapsible tree, with a built-in toolbar (zoom/fit controls from `markmap-toolbar`).

## States

- **Loading (tree)**: spinner + "Loading vault…" in the sidebar (`index.tsx:64-69`).
- **Error (tree)**: "Failed to load vault." in red, in the sidebar (`index.tsx:70`) — shown whenever `useVaultTree()` reports `isError` (e.g. the backend 404s because `/vault` isn't mounted).
- **Empty (tree)**: "No notes found in the vault." (italic, sidebar, `index.tsx:72-74`).
- **Empty (no note selected, Note view)**: "Select a note to read it." (`index.tsx:158-159`).
- **Loading (note content)**: spinner + "Loading note…" (`index.tsx:161-165`).
- **Loading (graph)**: spinner + "Building graph…" (`index.tsx:190-194`).
- **Empty/prompt (Mind map view, no note selected)**: "Select a note first." (`index.tsx:202`).
- **Error (save failed)**: inline red text "Failed to save: {message}" above the content (`index.tsx:167-171`), driven by `updateNote.isError`.
- **Error (delete failed)**: inline red text "Failed to delete: {message}" (`index.tsx:172-176`), driven by `deleteNote.isError`.
- **No explicit error state** for a failed `useVaultGraph()` or `useVaultNote()` fetch beyond TanStack Query's default (no graph/no note silently renders nothing extra — there's no dedicated "Failed to load graph"/"Failed to load note" message, unlike the tree and the save/delete mutations).

## Business Rules Surfaced Here

None — this is a filesystem-backed note browser/editor, outside ForgeHub's core domain model (`docs/DATA_MODEL.md`, `docs/BUSINESS_RULES.md` cover Product/Pipeline/Planning/Execution/Agent/Skill/Task/Governance only). The only constraints enforced are filesystem/path-safety ones, not business rules: notes must resolve inside the vault root and must have a `.md` extension (`backend/app/core/markdown_docs.py:54-60`, `backend/app/api/routes/vault.py:38-44`).

## Dependencies

- **Host bind mount**: `backend/app/api/routes/vault.py` reads `VAULT_ROOT = Path("/vault")` inside the container; `docker-compose.yml`'s `forgehub-backend` service mounts `/root/.hermes/knowledge_base/vault:/vault` (read-write) — confirmed consistent with the code. This was recently repointed from `/root/.hermes/foundation/vault` (per the task brief); the in-repo comment directly above the mount (`docker-compose.yml:27-30`) describes it as "backs the Obsidian vault browser/editor (api/routes/vault.py)". If `/root/.hermes/knowledge_base/vault` doesn't exist on the host, both `GET /tree` and `GET /graph` return 404 ("Vault is not mounted") and the screen shows the tree-load error state.
- **`backend/app/core/markdown_docs.py`** — shared tree/graph-building logic, also used by the unrelated `foundation_docs.py` router (Foundation rules browser, a different mount/screen). A change to this shared module affects both screens.
- **No database tables** — this screen has no SQLAlchemy model, no Alembic migration, and is not part of the `app/db/models/__init__.py` aggregation; everything is computed from the filesystem on each request (no caching layer in the backend beyond TanStack Query's client-side cache).
- **Third-party libraries**: `force-graph` (graph rendering, no React wrapper), `markmap-lib`/`markmap-view`/`markmap-toolbar` (mind map rendering), `react-markdown` + `remark-gfm` (note read view).

## Notes / Improvement Opportunities

- Concurrent-edit conflicts are explicitly accepted, not handled: the router's module docstring (`backend/app/api/routes/vault.py:10-14`) states that if a note is open in both ForgeHub and the desktop Obsidian app at once, "last write wins (no locking)" — there is no ETag/If-Match/optimistic-lock mechanism, and the frontend has no UI to detect or warn about this.
- Naming drift: the route (`/obsidian`), directory (`pages/obsidian/`), component name (`ObsidianPage`), hook file (`useVault.ts`), and query keys (`vault-tree`, `vault-note`, `vault-graph`) all still reference "Obsidian"/"vault" even though the sidebar-visible label is now "Knowledge Base" — purely cosmetic today, but a source of confusion if another contributor greps for "Knowledge Base" and finds nothing.
- No error state is rendered for a failed `useVaultGraph()` fetch — if the request errors (e.g. backend down, vault unmounted) after the tree already loaded successfully, switching to Graph view shows nothing (no spinner, no error text), since the page only checks `graphLoading` and `graph` truthiness (`index.tsx:190-197`), not `isError`.
- Similarly, `useVaultNote(path)` has no `isError` handling in the page — a failed note fetch (e.g. file deleted externally between tree load and click) leaves the Note pane blank with no feedback, since only `noteLoading` is checked, not error state (`index.tsx:161-166`, `184`).
- Delete confirmation uses a native `window.confirm` (`index.tsx:55`) rather than the app's own dialog/modal primitives — inconsistent with shadcn/ui-based confirm patterns likely used elsewhere, and not stylable/testable the same way.
- The Mind map view re-derives the heading outline from a note's full Markdown content on every render via `extractHeadings` (`MindMapView.tsx:18-30`), with no memoization beyond the `useEffect` dependency on `markdown` itself — acceptable given Markmap rebuilds its own tree each time anyway, but worth noting if note sizes grow significantly.
- Backend write path (`update_vault_note`, `vault.py:69-75`) requires the target file to already exist (404 otherwise) — this screen cannot be used to create new notes, only edit/delete existing ones; there is no "New Note" action anywhere in the UI.
