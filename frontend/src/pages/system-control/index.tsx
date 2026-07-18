import { useState } from "react";
import { Archive, ChevronDown, ChevronRight, GitBranch, GitCommit, Loader2, RefreshCw, Sparkles, Trash2 } from "lucide-react";
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
  useRunBackup,
  useRunCleanup,
  useSystemControlStatus,
} from "@/hooks/useSystemControl";
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

  const { data: scan, isLoading: scanLoading, isError: scanError } = useCleanupScan();
  const runCleanup = useRunCleanup();
  const [confirmingCleanup, setConfirmingCleanup] = useState(false);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

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
            </div>
            <div className="flex items-center gap-1.5">
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
            Read-only inventory of logs, backup files, cron output snapshots, and old/duplicate scripts. "Run
            Cleanup" executes the same weekly Athos policy used by the foundation-clear cron: clears trash, expires
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
          {scan && scan.categories.length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {scan.categories.map((cat) => {
                const expanded = expandedCategory === cat.category;
                return (
                  <button
                    key={cat.category}
                    type="button"
                    onClick={() => setExpandedCategory(expanded ? null : cat.category)}
                    className="rounded-md border border-border p-3 text-left hover:bg-accent"
                  >
                    <span className="flex items-center justify-between gap-1">
                      <span className="text-xs font-medium uppercase text-muted-foreground">{cat.category}</span>
                      {expanded ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )}
                    </span>
                    <span className="mt-1 block text-lg font-semibold">{cat.count} file(s)</span>
                    <span className="text-xs text-muted-foreground">{formatBytes(cat.total_size)}</span>
                  </button>
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
    </div>
  );
}
