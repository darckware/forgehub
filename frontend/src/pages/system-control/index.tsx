import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Archive, ChevronDown, ChevronRight, ExternalLink, GitBranch, GitCommit, Loader2, MessageSquare, RefreshCw, RotateCcw, Sparkles, SquareTerminal, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useBackupListing,
  useBackupTargets,
  useCleanupScan,
  useCommitChanges,
  useDeleteBackup,
  useDeleteCleanupCategory,
  useEmptyTrash,
  useRunBackup,
  useRunCleanup,
  useSystemControlStatus,
  useTrashStatus,
} from "@/hooks/useSystemControl";
import { useKillTerminalSession, useTerminalSessions } from "@/hooks/useTerminalBrowse";
import {
  useChatSessionsHostStatus,
  useDeleteChatSessionHostStatus,
  useResetAllStaleChatSessions,
  useResetChatSessionHermesLink,
} from "@/hooks/useChat";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function formatUnixDateTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString();
}

export default function SystemControlPage() {
  // undefined until the user picks something -- the backend defaults to
  // its own DEFAULT_REPO either way, this just lets the <Select> start
  // unset instead of guessing a key before the first response arrives.
  const [repo, setRepo] = useState<string | undefined>(undefined);
  const { data, isLoading, isError, error, refetch, isFetching } = useSystemControlStatus(repo);
  const commitMut = useCommitChanges();
  const [showCommitForm, setShowCommitForm] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");

  // "hermes" | "project:<uuid>" | "all" -- "all" has no listing (backups
  // stay separated by target on disk), only a "Backup all" action.
  const [backupTarget, setBackupTarget] = useState("hermes");
  const { data: backupTargets } = useBackupTargets();
  const { data: backupListing, isLoading: backupListingLoading } = useBackupListing(
    backupTarget === "all" ? "hermes" : backupTarget
  );
  const runBackup = useRunBackup();
  const deleteBackup = useDeleteBackup();
  const [deletingBackup, setDeletingBackup] = useState<string | null>(null);

  const { data: scan, isLoading: scanLoading, isFetching: scanFetching, isError: scanError } = useCleanupScan();
  const runCleanup = useRunCleanup();
  const [confirmingCleanup, setConfirmingCleanup] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const deleteCleanupCategory = useDeleteCleanupCategory();
  const { data: trashStatus } = useTrashStatus();
  const emptyTrash = useEmptyTrash();
  const [confirmingEmptyTrash, setConfirmingEmptyTrash] = useState(false);
  const [deletingCategory, setDeletingCategory] = useState<string | null>(null);

  const { data: terminalSessions, isLoading: terminalSessionsLoading } = useTerminalSessions();
  const killTerminalSession = useKillTerminalSession();
  const [killingSession, setKillingSession] = useState<string | null>(null);

  const { data: chatSessions, isLoading: chatSessionsLoading } = useChatSessionsHostStatus();
  const resetChatSession = useResetChatSessionHermesLink();
  const [resettingChatSession, setResettingChatSession] = useState<{ sessionId: string; participantId: string | null } | null>(
    null
  );
  const deleteChatSession = useDeleteChatSessionHostStatus();
  const [deletingChatSession, setDeletingChatSession] = useState<{ sessionId: string; title: string } | null>(null);
  const resetAllStaleChatSessions = useResetAllStaleChatSessions();
  const [confirmingResetAllStale, setConfirmingResetAllStale] = useState(false);
  const staleChatSessions = (chatSessions ?? []).filter((s) => !s.running && !s.exists);
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading system control...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        Failed to load system control: {(error as Error)?.message ?? "unknown error"}
      </div>
    );
  }

  const dirtyCount = data.git.dirty_count;
  const lastCommit = data.git.last_commit;
  const targets = backupTargets?.targets ?? [];
  const selectedTarget = targets.find((t) => t.key === backupTarget);
  const isAllBackups = backupTarget === "all";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Control</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Git status for registered projects and compressed backups written to /root/backup.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching} className="gap-2">
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
          <AssistantToggleButton className="gap-2" />
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">Branch</p>
            <p className="mt-1 truncate text-lg font-semibold">{data.git.branch}</p>
            <p className="mt-1 text-xs text-muted-foreground">{data.git.short_head}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">Working tree</p>
            <p className="mt-1 text-lg font-semibold">{dirtyCount === 0 ? "Clean" : `${dirtyCount} file(s)`}</p>
            <p className="mt-1 text-xs text-muted-foreground">Repository root: {data.git.repo_root}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">Last commit</p>
            <p className="mt-1 truncate text-lg font-semibold">{lastCommit.subject ?? "No commit"}</p>
            <p className="mt-1 text-xs text-muted-foreground">{lastCommit.author ?? "Unknown author"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">Hermes backups</p>
            <p className="mt-1 text-lg font-semibold">{data.backups.count} archive(s)</p>
            <p className="mt-1 text-xs text-muted-foreground">{data.backups.path}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">Git Control</h2>
              </div>
              <div className="flex items-center gap-1.5">
                <Select
                  value={data.git.repo_key}
                  className="h-8 w-40 text-xs"
                  onChange={(e) => setRepo(e.target.value)}
                  aria-label="Repository"
                >
                  <optgroup label="System">
                    {data.available_repos
                      .filter((r) => r.kind === "system")
                      .map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.label}
                        </option>
                      ))}
                  </optgroup>
                  {data.available_repos.some((r) => r.kind === "project") && (
                    <optgroup label="Projects">
                      {data.available_repos
                        .filter((r) => r.kind === "project")
                        .map((r) => (
                          <option key={r.key} value={r.key}>
                            {r.label}
                          </option>
                        ))}
                    </optgroup>
                  )}
                </Select>
                <Button
                  size="sm"
                  variant={showCommitForm ? "secondary" : "outline"}
                  className="gap-1.5"
                  disabled={dirtyCount === 0}
                  title={dirtyCount === 0 ? "Nothing to commit" : "Commit all pending changes"}
                  onClick={() => setShowCommitForm((v) => !v)}
                >
                  <GitCommit className="h-3.5 w-3.5" /> Commit
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              "Hermes" plus every registered project with a working directory -- add one from the project's own
              registration page, not here.
            </p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">Commit</span>
                <span className="font-mono text-xs">{lastCommit.hash.slice(0, 12)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">Status</span>
                <Badge variant={dirtyCount === 0 ? "success" : "destructive"}>
                  {dirtyCount === 0 ? "Clean" : "Changes pending"}
                </Badge>
              </div>
            </div>
            {showCommitForm && (
              <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
                <Input
                  autoFocus
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  placeholder="Commit message"
                  maxLength={500}
                  className="h-8 text-xs"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && commitMessage.trim() && !commitMut.isPending) {
                      commitMut.mutate(
                        { message: commitMessage.trim(), repo: data.git.repo_key },
                        { onSuccess: () => { setShowCommitForm(false); setCommitMessage(""); } }
                      );
                    }
                  }}
                />
                {/* Stages everything (git add -A) -- see CommitRequest's docstring
                    in backend/app/api/routes/system_control.py. Never pushes. */}
                <p className="text-[11px] text-muted-foreground">
                  Stages all {dirtyCount} pending file(s) and commits. Does not push.
                </p>
                {commitMut.isError && (
                  <p className="text-xs text-destructive">
                    {(commitMut.error as Error)?.message ?? "Commit failed"}
                  </p>
                )}
                <div className="flex justify-end gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setShowCommitForm(false);
                      setCommitMessage("");
                    }}
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    disabled={!commitMessage.trim() || commitMut.isPending}
                    onClick={() =>
                      commitMut.mutate(
                        { message: commitMessage.trim(), repo: data.git.repo_key },
                        { onSuccess: () => { setShowCommitForm(false); setCommitMessage(""); } }
                      )
                    }
                  >
                    {commitMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Commit"}
                  </Button>
                </div>
              </div>
            )}
            {data.git.status_lines.length > 0 ? (
              <pre className="max-h-56 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
                {data.git.status_lines.join("\n")}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No modified files.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Archive className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">Backups</h2>
              </div>
              <div className="flex items-center gap-1.5">
                <Select
                  value={backupTarget}
                  className="h-8 w-40 text-xs"
                  onChange={(e) => setBackupTarget(e.target.value)}
                  aria-label="Backup target"
                >
                  {targets.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.label}
                    </option>
                  ))}
                  {targets.length > 1 && <option value="all">All</option>}
                </Select>
                <Button
                  size="sm"
                  onClick={() => runBackup.mutate({ target: backupTarget })}
                  disabled={runBackup.isPending || (selectedTarget != null && !selectedTarget.ready)}
                  className="gap-2"
                  title={
                    selectedTarget && !selectedTarget.ready
                      ? "This project has no working directory set yet"
                      : undefined
                  }
                >
                  {runBackup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
                  Backup {isAllBackups ? "all" : "now"}
                </Button>
              </div>
            </div>
            {!isAllBackups && selectedTarget && (
              <p className="font-mono text-xs text-muted-foreground">
                {selectedTarget.source ?? "(no working directory set)"} → {selectedTarget.location}
              </p>
            )}
            <p className="text-[11px] text-muted-foreground">
              Archives are kept separate per target -- Hermes and each project write to their own directory, never
              intermixed. Enable backup for a project from its own registration page.
            </p>
            {runBackup.isSuccess && (
              <div className="space-y-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
                {runBackup.data.results.map((r) => (
                  <p key={r.target}>
                    {r.label}: created {r.archive_path} ({formatBytes(r.size_bytes)})
                  </p>
                ))}
                {runBackup.data.errors.map((e) => (
                  <p key={e.target} className="text-destructive">
                    {e.target}: {e.detail}
                  </p>
                ))}
              </div>
            )}
            {runBackup.isError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {(runBackup.error as Error)?.message ?? "Backup failed"}
              </div>
            )}
            {deleteBackup.isError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {(deleteBackup.error as Error)?.message ?? "Failed to delete backup"}
              </div>
            )}
            <ConfirmDialog
              open={deletingBackup !== null}
              title={`Delete "${deletingBackup ?? ""}"`}
              description="Permanently removes this backup archive. This action cannot be undone."
              loading={deleteBackup.isPending}
              onConfirm={() => {
                if (deletingBackup) {
                  deleteBackup.mutate(
                    { target: backupTarget, filename: deletingBackup },
                    { onSuccess: () => setDeletingBackup(null) }
                  );
                }
              }}
              onCancel={() => setDeletingBackup(null)}
            />
            {isAllBackups ? (
              <p className="text-sm text-muted-foreground">
                Pick a single target above to browse or delete its archives -- "All" is only for running backups.
              </p>
            ) : backupListingLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading archives...
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Archive</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(backupListing?.entries ?? []).map((entry) => (
                    <TableRow key={entry.path}>
                      <TableCell className="font-mono text-xs">{entry.name}</TableCell>
                      <TableCell>{formatBytes(entry.size)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          aria-label={`Delete ${entry.name}`}
                          title={`Delete ${entry.name}`}
                          onClick={() => setDeletingBackup(entry.name)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {(backupListing?.entries ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={3} className="text-sm text-muted-foreground">
                        No backup archives found{backupListing ? ` in ${backupListing.path}` : ""}.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">Cleanup</h2>
              {scan && (
                <span className="text-xs text-muted-foreground">
                  {scan.total_count} file(s), {formatBytes(scan.total_size)} under {scan.root}
                </span>
              )}
              {scanFetching && !scanLoading && (
                <span
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                  title="A category was just cleared -- the host filesystem is being re-scanned in the background, counts below are still catching up"
                >
                  <Loader2 className="h-3 w-3 animate-spin" /> Updating…
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmingEmptyTrash(true)}
                disabled={!trashStatus || trashStatus.item_count === 0 || emptyTrash.isPending}
                className="gap-2 text-destructive hover:text-destructive"
                title="Permanently deletes everything moved to trash by the buttons below -- unlike them, this cannot be undone"
              >
                {emptyTrash.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Empty trash{" "}
                {trashStatus && trashStatus.item_count > 0
                  ? `(${trashStatus.item_count} item(s), ${formatBytes(trashStatus.total_size)})`
                  : ""}
              </Button>
              <Button
                size="sm"
                onClick={() => setConfirmingCleanup(true)}
                disabled={runCleanup.isPending}
                className="gap-2"
                title="Runs the same bounded cleanup policy used by the weekly Athos cron"
              >
                {runCleanup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Run Cleanup
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Read-only inventory of logs, backup files, cron output snapshots, and old/duplicate scripts. Files
            cleared here (individually or via "Run Cleanup") are moved to trash, not deleted -- use "Empty trash"
            above to permanently remove what has accumulated there. "Run Cleanup" also executes the same weekly
            Athos policy used by the foundation-clear cron: expires
            manual backups after 30 days, bounds temporary files and journals, and prunes all inactive reproducible Docker cache,
            stopped containers, dangling images, and unused networks. Docker volumes, databases, live agent logs,
            sessions, knowledge, and scripts are never deleted by this action.
          </p>
          <ConfirmDialog
            open={confirmingCleanup}
            title="Run ecosystem cleanup?"
            description="Runs the weekly Athos cleanup now. Expired files and trash are permanently deleted, and reproducible Docker artifacts are pruned. Docker volumes and databases are excluded."
            confirmLabel="Run cleanup"
            loading={runCleanup.isPending}
            onConfirm={() =>
              runCleanup.mutate(undefined, { onSuccess: () => setConfirmingCleanup(false) })
            }
            onCancel={() => setConfirmingCleanup(false)}
          />
          {emptyTrash.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(emptyTrash.error as Error)?.message ?? "Failed to empty trash"}
            </div>
          )}
          <ConfirmDialog
            open={confirmingEmptyTrash}
            title={
              trashStatus
                ? `Permanently delete ${trashStatus.item_count} item(s) (${formatBytes(trashStatus.total_size)}) from trash?`
                : "Permanently delete everything in trash?"
            }
            description="Everything currently in trash -- from every category clear and every Run Cleanup so far -- is deleted for good. This cannot be undone and is not part of the weekly policy; it only runs when you click this button."
            confirmLabel="Empty trash"
            loading={emptyTrash.isPending}
            onConfirm={() => emptyTrash.mutate(undefined, { onSuccess: () => setConfirmingEmptyTrash(false) })}
            onCancel={() => setConfirmingEmptyTrash(false)}
          />
          {runCleanup.isSuccess && (
            <div className="space-y-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs">
              <p>Weekly ecosystem cleanup completed with policy <span className="font-mono">{runCleanup.data.policy}</span>.</p>
              <pre className="whitespace-pre-wrap">{runCleanup.data.output}</pre>
            </div>
          )}
          {runCleanup.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(runCleanup.error as Error)?.message ?? "Cleanup failed"}
            </div>
          )}
          {scanLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Scanning...
            </div>
          )}
          {scanError && <p className="text-sm text-destructive">Failed to scan for cleanup candidates.</p>}
          {scan && scan.categories.length === 0 && (
            <p className="text-sm text-muted-foreground">Nothing found.</p>
          )}
          {deleteCleanupCategory.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(deleteCleanupCategory.error as Error)?.message ?? "Failed to clear category"}
            </div>
          )}
          <ConfirmDialog
            open={deletingCategory !== null}
            title={`Clear "${deletingCategory ?? ""}"?`}
            description="Moves every file currently in this category to the trash root -- not a hard delete, so it stays recoverable there. The full weekly cleanup policy is unaffected."
            confirmLabel="Clear category"
            loading={deleteCleanupCategory.isPending}
            onConfirm={() => {
              if (deletingCategory) {
                deleteCleanupCategory.mutate(deletingCategory, {
                  onSuccess: () => {
                    setDeletingCategory(null);
                    setExpandedCategory((current) => (current === deletingCategory ? null : current));
                  },
                });
              }
            }}
            onCancel={() => setDeletingCategory(null)}
          />
          {scan && scan.categories.length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {scan.categories.map((cat) => {
                const expanded = expandedCategory === cat.category;
                return (
                  <div
                    key={cat.category}
                    role="button"
                    tabIndex={0}
                    onClick={() => setExpandedCategory(expanded ? null : cat.category)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpandedCategory(expanded ? null : cat.category);
                      }
                    }}
                    className="cursor-pointer rounded-md border border-border p-3 text-left hover:bg-accent"
                  >
                    <span className="flex items-center justify-between gap-1">
                      <span className="text-xs font-medium uppercase text-muted-foreground">{cat.category}</span>
                      <span className="flex shrink-0 items-center gap-0.5">
                        <button
                          type="button"
                          className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          aria-label={`Clear ${cat.category}`}
                          title={`Clear ${cat.category}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeletingCategory(cat.category);
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                        {expanded ? (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </span>
                    </span>
                    <span className="mt-1 block text-lg font-semibold">{cat.count} file(s)</span>
                    <span className="text-xs text-muted-foreground">{formatBytes(cat.total_size)}</span>
                  </div>
                );
              })}
            </div>
          )}
          {expandedCategory && (
            <div className="max-h-64 space-y-1 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
              {scan?.categories
                .find((c) => c.category === expandedCategory)
                ?.files.map((f) => (
                  <div key={f.path} className="flex items-center justify-between gap-3">
                    <span className="min-w-0 flex-1 truncate" title={f.path}>{f.path}</span>
                    <span className="shrink-0 text-muted-foreground">{formatDateTime(f.mtime)}</span>
                    <span className="shrink-0 text-muted-foreground">{formatBytes(f.size)}</span>
                  </div>
                ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <SquareTerminal className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">Terminal Sessions</h2>
              {terminalSessions && (
                <span className="text-xs text-muted-foreground">
                  {terminalSessions.sessions.length} live tmux session(s)
                </span>
              )}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Every live <span className="font-mono">forgehub-*</span> tmux session on the host, whether or not a
            Workspace tab is currently attached to it. A tab closed by a browser crash or a page reload outside the
            Workspace's own close button leaves its session running here indefinitely -- kill it to free it up.
            ForgeHub keeps no separate record of terminal tabs; this is a live read of the host itself.
          </p>
          {terminalSessionsLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading sessions...
            </div>
          )}
          {killTerminalSession.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(killTerminalSession.error as Error)?.message ?? "Failed to kill session"}
            </div>
          )}
          <ConfirmDialog
            open={killingSession !== null}
            title="Kill this terminal session?"
            description="Ends the tmux session and any process still running inside it (shell, CLI agent, etc). This cannot be undone."
            confirmLabel="Kill session"
            loading={killTerminalSession.isPending}
            onConfirm={() => {
              if (killingSession) {
                killTerminalSession.mutate(killingSession, { onSuccess: () => setKillingSession(null) });
              }
            }}
            onCancel={() => setKillingSession(null)}
          />
          {!terminalSessionsLoading && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead>Attached</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(terminalSessions?.sessions ?? []).map((s) => (
                  <TableRow key={s.session_id}>
                    <TableCell className="font-mono text-xs">{s.session_id}</TableCell>
                    <TableCell>
                      <Badge variant={s.attached ? "success" : "outline"}>
                        {s.attached ? "Attached" : "Orphaned"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">{formatUnixDateTime(s.created_at)}</TableCell>
                    <TableCell className="text-xs">{formatUnixDateTime(s.last_activity_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={`Open session ${s.session_id} in Workspace`}
                          title="Open in Workspace"
                          onClick={() =>
                            navigate("/workspace", {
                              state: { openSession: { id: s.session_id, label: s.session_id.slice(0, 8) } },
                            })
                          }
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          aria-label={`Kill session ${s.session_id}`}
                          title={`Kill session ${s.session_id}`}
                          onClick={() => setKillingSession(s.session_id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {(terminalSessions?.sessions ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-sm text-muted-foreground">
                      No live terminal sessions.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">Chat Sessions</h2>
              {chatSessions && (
                <span className="text-xs text-muted-foreground">{chatSessions.length} tracked session(s)</span>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setConfirmingResetAllStale(true)}
              disabled={staleChatSessions.length === 0 || resetAllStaleChatSessions.isPending}
              title="Resets every session currently showing Stale, one confirm instead of one row at a time"
            >
              {resetAllStaleChatSessions.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
              Reset all stale ({staleChatSessions.length})
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Every Workspace conversation with a Hermes agent that has a resumed session, checked against that
            profile's own session store on the host. A conversation can go "Stale" without any action here -- the
            underlying Hermes session was pruned or rebuilt on the host -- and every message sent to it afterwards
            fails the same way until reset. Reset only forgets the resume link on ForgeHub's side; it never touches
            Hermes' own conversation history.
          </p>
          {chatSessionsLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading sessions...
            </div>
          )}
          {resetChatSession.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(resetChatSession.error as Error)?.message ?? "Failed to reset session"}
            </div>
          )}
          <ConfirmDialog
            open={resettingChatSession !== null}
            title="Reset this chat session?"
            description="Forgets the resumed Hermes session so the next message starts a fresh one. The conversation history in ForgeHub is kept; only continuity on the Hermes side is lost. Use this when the session shows Stale."
            confirmLabel="Reset session"
            loading={resetChatSession.isPending}
            onConfirm={() => {
              if (resettingChatSession) {
                resetChatSession.mutate(
                  { sessionId: resettingChatSession.sessionId, participantId: resettingChatSession.participantId },
                  { onSuccess: () => setResettingChatSession(null) }
                );
              }
            }}
            onCancel={() => setResettingChatSession(null)}
          />
          {resetAllStaleChatSessions.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(resetAllStaleChatSessions.error as Error)?.message ?? "Failed to reset one or more sessions"}
            </div>
          )}
          <ConfirmDialog
            open={confirmingResetAllStale}
            title={`Reset ${staleChatSessions.length} stale session(s)?`}
            description="Forgets the resumed Hermes session for every session currently showing Stale, so the next message on each starts a fresh one. Conversation history in ForgeHub is kept; only continuity on the Hermes side is lost."
            confirmLabel="Reset all stale"
            loading={resetAllStaleChatSessions.isPending}
            onConfirm={() => {
              resetAllStaleChatSessions.mutate(
                staleChatSessions.map((s) => ({ sessionId: s.session_id, participantId: s.participant_id })),
                { onSuccess: () => setConfirmingResetAllStale(false) }
              );
            }}
            onCancel={() => setConfirmingResetAllStale(false)}
          />
          {deleteChatSession.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(deleteChatSession.error as Error)?.message ?? "Failed to delete session"}
            </div>
          )}
          <ConfirmDialog
            open={deletingChatSession !== null}
            title="Delete this chat session?"
            description={`Permanently deletes "${deletingChatSession?.title ?? ""}" and every message in it from ForgeHub. This cannot be undone.`}
            confirmLabel="Delete session"
            loading={deleteChatSession.isPending}
            onConfirm={() => {
              if (deletingChatSession) {
                deleteChatSession.mutate(deletingChatSession.sessionId, {
                  onSuccess: () => setDeletingChatSession(null),
                });
              }
            }}
            onCancel={() => setDeletingChatSession(null)}
          />
          {!chatSessionsLoading && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Session</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead className="w-28" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(chatSessions ?? []).map((s) => (
                  <TableRow key={`${s.session_id}:${s.participant_id ?? "owner"}`}>
                    <TableCell className="text-sm">{s.agent_name}</TableCell>
                    <TableCell className="max-w-[240px] truncate text-sm" title={s.session_title}>
                      {s.session_title}
                    </TableCell>
                    <TableCell>
                      <Badge variant={s.running ? "default" : s.exists ? "success" : "destructive"}>
                        {s.running ? "Running" : s.exists ? "Live" : "Stale"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {s.last_activity_at != null ? formatUnixDateTime(s.last_activity_at) : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          aria-label={`Open ${s.session_title} in Workspace`}
                          title="Open in Workspace"
                          onClick={() =>
                            navigate("/workspace", { state: { openChatSession: { agentId: s.agent_id, sessionId: s.session_id } } })
                          }
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          aria-label={`Reset ${s.session_title}`}
                          title="Reset Hermes session"
                          onClick={() => setResettingChatSession({ sessionId: s.session_id, participantId: s.participant_id })}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          aria-label={`Delete ${s.session_title}`}
                          title="Delete session"
                          onClick={() => setDeletingChatSession({ sessionId: s.session_id, title: s.session_title })}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {(chatSessions ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-sm text-muted-foreground">
                      No tracked chat sessions.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
