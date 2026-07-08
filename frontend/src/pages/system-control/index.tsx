import { Archive, GitBranch, Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useHermesBackup, useSystemControlStatus } from "@/hooks/useSystemControl";

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
  const { data, isLoading, isError, error, refetch, isFetching } = useSystemControlStatus();
  const backupMut = useHermesBackup();

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
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">Git Control</h2>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Archive</TableHead>
                  <TableHead>Size</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.backups.entries.map((entry) => (
                  <TableRow key={entry.path}>
                    <TableCell className="font-mono text-xs">{entry.name}</TableCell>
                    <TableCell>{formatBytes(entry.size)}</TableCell>
                  </TableRow>
                ))}
                {data.backups.entries.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} className="text-sm text-muted-foreground">
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
