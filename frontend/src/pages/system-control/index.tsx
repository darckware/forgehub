import { useState } from "react";
import { Archive, GitBranch, GitCommit, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCommitChanges, useDeleteBackup, useHermesBackup, useSystemControlStatus } from "@/hooks/useSystemControl";

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

export default function SystemControlPage() {
  // undefined until the user picks something -- the backend defaults to
  // its own DEFAULT_REPO either way, this just lets the <Select> start
  // unset instead of guessing a key before the first response arrives.
  const [repo, setRepo] = useState<string | undefined>(undefined);
  const { data, isLoading, isError, error, refetch, isFetching } = useSystemControlStatus(repo);
  const backupMut = useHermesBackup();
  const deleteBackup = useDeleteBackup();
  const [deletingBackup, setDeletingBackup] = useState<string | null>(null);
  const commitMut = useCommitChanges();
  const [showCommitForm, setShowCommitForm] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");

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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">System Control</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Git status for this repository and compressed Hermes backups written to /root/backup.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching} className="gap-2">
          {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
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
                  className="h-8 w-32 text-xs"
                  onChange={(e) => setRepo(e.target.value)}
                  aria-label="Repository"
                >
                  {data.available_repos.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.key}
                    </option>
                  ))}
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
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Archive className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">Hermes Backup</h2>
              </div>
              <Button
                size="sm"
                onClick={() => backupMut.mutate()}
                disabled={backupMut.isPending}
                className="gap-2"
              >
                {backupMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
                Backup .hermes
              </Button>
            </div>
            {backupMut.isSuccess && (
              <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
                Created {backupMut.data.archive_path} ({formatBytes(backupMut.data.size_bytes)})
              </div>
            )}
            {backupMut.isError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {(backupMut.error as Error)?.message ?? "Backup failed"}
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
              description="Permanently removes this backup archive from /root/backup. This action cannot be undone."
              loading={deleteBackup.isPending}
              onConfirm={() => {
                if (deletingBackup) deleteBackup.mutate(deletingBackup, { onSuccess: () => setDeletingBackup(null) });
              }}
              onCancel={() => setDeletingBackup(null)}
            />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Archive</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.backups.entries.map((entry) => (
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
                {data.backups.entries.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-sm text-muted-foreground">
                      No backup archives found in /root/backup.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
