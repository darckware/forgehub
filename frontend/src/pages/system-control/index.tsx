import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Archive, ChevronDown, ChevronRight, ExternalLink, GitBranch, GitCommit, Loader2, MessageSquare, RefreshCw, RotateCcw, Sparkles, SquareTerminal, Trash2, X } from "lucide-react";
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
import { DockerCleanupCard } from "./DockerCleanupCard";
import { BackupFilesCard } from "./BackupFilesCard";

function formatByteValue(bytes: number | null | undefined, locale: string): string {
  if (bytes == null) return "—";
  const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  if (bytes < 1024) return `${number.format(bytes)} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${number.format(kb)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${number.format(mb)} MB`;
  return `${number.format(mb / 1024)} GB`;
}

function formatDateTimeValue(iso: string, locale: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale);
}

function formatUnixDateTimeValue(unixSeconds: number, locale: string): string {
  return new Date(unixSeconds * 1000).toLocaleString(locale);
}

export default function SystemControlPage() {
  const { t, i18n } = useTranslation("systemControl");
  const formatBytes = (bytes: number | null | undefined) => formatByteValue(bytes, i18n.language);
  const formatDateTime = (iso: string) => formatDateTimeValue(iso, i18n.language);
  const formatUnixDateTime = (seconds: number) => formatUnixDateTimeValue(seconds, i18n.language);
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

  const { data: scan, isLoading: scanLoading, isFetching: scanFetching, isError: scanError, refetch: refetchScan } = useCleanupScan();
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
        {t("page.loading")}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {t("page.loadFailed", { error: (error as Error)?.message ?? t("page.unknownError") })}
      </div>
    );
  }

  const dirtyCount = data.git.dirty_count;
  const lastCommit = data.git.last_commit;
  const targets = backupTargets?.targets ?? [];
  const selectedTarget = targets.find((t) => t.key === backupTarget);
  const isAllBackups = backupTarget === "all";

  return (
    <div className="space-y-6 max-md:break-words">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("page.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("page.description")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching} className="gap-2">
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {t("page.refresh")}
          </Button>
          <AssistantToggleButton className="gap-2" />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("page.branch")}</p>
            <p className="mt-1 truncate text-lg font-semibold">{data.git.branch}</p>
            <p className="mt-1 text-xs text-muted-foreground">{data.git.short_head}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("page.workingTree")}</p>
            <p className="mt-1 text-lg font-semibold">{dirtyCount === 0 ? t("page.clean") : t("page.files", { count: dirtyCount })}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("page.repositoryRoot", { path: data.git.repo_root })}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("page.lastCommit")}</p>
            <p className="mt-1 truncate text-lg font-semibold">{lastCommit.subject ?? t("page.noCommit")}</p>
            <p className="mt-1 text-xs text-muted-foreground">{lastCommit.author ?? t("page.unknownAuthor")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("page.hermesBackups")}</p>
            <p className="mt-1 text-lg font-semibold">{t("page.archives", { count: data.backups.count })}</p>
            <p className="mt-1 text-xs text-muted-foreground">{data.backups.path}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">{t("git.title")}</h2>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Select
                  value={data.git.repo_key}
                  className="h-8 w-40 text-xs"
                  onChange={(e) => setRepo(e.target.value)}
                  aria-label={t("git.repository")}
                >
                  <optgroup label={t("git.system")}>
                    {data.available_repos
                      .filter((r) => r.kind === "system")
                      .map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.label}
                        </option>
                      ))}
                  </optgroup>
                  {data.available_repos.some((r) => r.kind === "project") && (
                    <optgroup label={t("git.projects")}>
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
                  title={dirtyCount === 0 ? t("git.nothingToCommit") : t("git.commitAllTitle")}
                  onClick={() => setShowCommitForm((v) => !v)}
                >
                  <GitCommit className="h-3.5 w-3.5" /> {t("git.commit")}
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {t("git.description")}
            </p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t("git.commit")}</span>
                <span className="font-mono text-xs">{lastCommit.hash.slice(0, 12)}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t("git.status")}</span>
                <Badge variant={dirtyCount === 0 ? "success" : "destructive"}>
                  {dirtyCount === 0 ? t("page.clean") : t("git.changesPending")}
                </Badge>
              </div>
            </div>
            {showCommitForm && (
              <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
                <Input
                  autoFocus
                  value={commitMessage}
                  onChange={(e) => setCommitMessage(e.target.value)}
                  placeholder={t("git.commitMessage")}
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
                  {t("git.stageAndCommit", { count: dirtyCount })}
                </p>
                {commitMut.isError && (
                  <p className="text-xs text-destructive">
                    {(commitMut.error as Error)?.message ?? t("git.commitFailed")}
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
                    {t("page.cancel")}
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
                    {commitMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("git.commit")}
                  </Button>
                </div>
              </div>
            )}
            {data.git.status_lines.length > 0 ? (
              <pre className="max-h-56 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
                {data.git.status_lines.join("\n")}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">{t("git.noModifiedFiles")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Archive className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">{t("backups.title")}</h2>
              </div>
              <div className="flex items-center gap-1.5">
                <Select
                  value={backupTarget}
                  className="h-8 w-40 text-xs"
                  onChange={(e) => setBackupTarget(e.target.value)}
                  aria-label={t("backups.target")}
                >
                  {targets.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.label}
                    </option>
                  ))}
                  {targets.length > 1 && <option value="all">{t("backups.all")}</option>}
                </Select>
                <Button
                  size="sm"
                  onClick={() => runBackup.mutate({ target: backupTarget })}
                  disabled={runBackup.isPending || (selectedTarget != null && !selectedTarget.ready)}
                  className="gap-2"
                  title={
                    selectedTarget && !selectedTarget.ready
                      ? t("backups.noWorkingDirectory")
                      : undefined
                  }
                >
                  {runBackup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Archive className="h-4 w-4" />}
                  {isAllBackups ? t("backups.runAll") : t("backups.runNow")}
                </Button>
              </div>
            </div>
            {!isAllBackups && selectedTarget && (
              <p className="font-mono text-xs text-muted-foreground">
                {selectedTarget.source ?? t("backups.noWorkingDirectoryShort")} → {selectedTarget.location}
              </p>
            )}
            <p className="text-[11px] text-muted-foreground">
              {t("backups.description")}
            </p>
            {runBackup.isSuccess && (
              <div className="space-y-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
                {runBackup.data.results.map((r) => (
                  <p key={r.target}>
                    {t("backups.created", { label: r.label, path: r.archive_path, size: formatBytes(r.size_bytes) })}
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
                {(runBackup.error as Error)?.message ?? t("backups.failed")}
              </div>
            )}
            {deleteBackup.isError && (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {(deleteBackup.error as Error)?.message ?? t("backups.deleteFailed")}
              </div>
            )}
            <ConfirmDialog
              open={deletingBackup !== null}
              title={t("backups.deleteTitle", { name: deletingBackup ?? "" })}
              description={t("backups.deleteDescription")}
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
                {t("backups.pickTarget")}
              </p>
            ) : backupListingLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> {t("backups.loadingArchives")}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("backups.archive")}</TableHead>
                    <TableHead>{t("backups.size")}</TableHead>
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
                          aria-label={t("backups.deleteName", { name: entry.name })}
                          title={t("backups.deleteName", { name: entry.name })}
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
                        {backupListing
                          ? t("backups.noArchivesAt", { path: backupListing.path })
                          : t("backups.noArchives")}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <DockerCleanupCard />

      <BackupFilesCard />

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">{t("cleanup.title")}</h2>
              {scan && (
                <span className="text-xs text-muted-foreground">
                  {t("cleanup.summary", { count: scan.total_count, size: formatBytes(scan.total_size), root: scan.root })}
                </span>
              )}
              {scanFetching && !scanLoading && (
                <span
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                  title={t("cleanup.updatingTitle")}
                >
                  <Loader2 className="h-3 w-3 animate-spin" /> {t("cleanup.updating")}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void refetchScan()}
                disabled={scanLoading || scanFetching}
                className="gap-2"
                title={t("cleanup.rescanTitle")}
              >
                <RefreshCw className={`h-4 w-4 ${scanFetching ? "animate-spin" : ""}`} />
                {t("cleanup.rescan")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmingEmptyTrash(true)}
                disabled={!trashStatus || trashStatus.item_count === 0 || emptyTrash.isPending}
                className="gap-2 text-destructive hover:text-destructive"
                title={t("cleanup.emptyTrashTitle")}
              >
                {emptyTrash.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                {t("cleanup.emptyTrash")}{" "}
                {trashStatus && trashStatus.item_count > 0
                  ? t("cleanup.trashSummary", { count: trashStatus.item_count, size: formatBytes(trashStatus.total_size) })
                  : ""}
              </Button>
              <Button
                size="sm"
                onClick={() => setConfirmingCleanup(true)}
                disabled={runCleanup.isPending}
                className="gap-2"
                title={t("cleanup.runTitle")}
              >
                {runCleanup.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                {t("cleanup.run")}
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {t("cleanup.description")}
          </p>
          <ConfirmDialog
            open={confirmingCleanup}
            title={t("cleanup.runConfirmTitle")}
            description={t("cleanup.runConfirmDescription")}
            confirmLabel={t("cleanup.run")}
            loading={runCleanup.isPending}
            onConfirm={() =>
              runCleanup.mutate(undefined, { onSuccess: () => setConfirmingCleanup(false) })
            }
            onCancel={() => setConfirmingCleanup(false)}
          />
          {emptyTrash.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(emptyTrash.error as Error)?.message ?? t("cleanup.emptyFailed")}
            </div>
          )}
          <ConfirmDialog
            open={confirmingEmptyTrash}
            title={
              trashStatus
                ? t("cleanup.emptyConfirmCount", { count: trashStatus.item_count, size: formatBytes(trashStatus.total_size) })
                : t("cleanup.emptyConfirmAll")
            }
            description={t("cleanup.emptyConfirmDescription")}
            confirmLabel={t("cleanup.emptyTrash")}
            loading={emptyTrash.isPending}
            onConfirm={() => emptyTrash.mutate(undefined, { onSuccess: () => setConfirmingEmptyTrash(false) })}
            onCancel={() => setConfirmingEmptyTrash(false)}
          />
          {runCleanup.isSuccess && (
            <div className="relative space-y-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs">
              <button
                type="button"
                aria-label={t("cleanup.dismissBanner")}
                title={t("cleanup.dismiss")}
                onClick={() => runCleanup.reset()}
                className="absolute right-2 top-2 rounded p-1 text-muted-foreground hover:bg-emerald-500/20 hover:text-foreground transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
              <p className="pr-6 font-medium text-emerald-600 dark:text-emerald-400">
                {t("cleanup.completed", { policy: runCleanup.data.policy })}
              </p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">{runCleanup.data.output}</pre>
            </div>
          )}
          {runCleanup.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(runCleanup.error as Error)?.message ?? t("cleanup.failed")}
            </div>
          )}
          {scanLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> {t("cleanup.scanning")}
            </div>
          )}
          {scanError && <p className="text-sm text-destructive">{t("cleanup.scanFailed")}</p>}
          {scan && scan.categories.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("cleanup.empty")}</p>
          )}
          {deleteCleanupCategory.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(deleteCleanupCategory.error as Error)?.message ?? t("cleanup.clearFailed")}
            </div>
          )}
          <ConfirmDialog
            open={deletingCategory !== null}
            title={t("cleanup.clearTitle", { category: deletingCategory ?? "" })}
            description={t("cleanup.clearDescription")}
            confirmLabel={t("cleanup.clearCategory")}
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
                      <span className="text-xs font-medium uppercase text-muted-foreground">{t(`cleanup.categories.${cat.category}`, { defaultValue: cat.category })}</span>
                      <span className="flex shrink-0 items-center gap-0.5">
                        <button
                          type="button"
                          className="rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          aria-label={t("cleanup.clearNamed", { category: t(`cleanup.categories.${cat.category}`, { defaultValue: cat.category }) })}
                          title={t("cleanup.clearNamed", { category: t(`cleanup.categories.${cat.category}`, { defaultValue: cat.category }) })}
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
                    <span className="mt-1 block text-lg font-semibold">{t("page.files", { count: cat.count })}</span>
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
              <h2 className="text-base font-semibold">{t("terminal.title")}</h2>
              {terminalSessions && (
                <span className="text-xs text-muted-foreground">
                  {t("terminal.liveCount", { count: terminalSessions.sessions.length })}
                </span>
              )}
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t("terminal.description")}
          </p>
          {terminalSessionsLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> {t("terminal.loading")}
            </div>
          )}
          {killTerminalSession.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(killTerminalSession.error as Error)?.message ?? t("terminal.killFailed")}
            </div>
          )}
          <ConfirmDialog
            open={killingSession !== null}
            title={t("terminal.killTitle")}
            description={t("terminal.killDescription")}
            confirmLabel={t("terminal.kill")}
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
                  <TableHead>{t("terminal.session")}</TableHead>
                  <TableHead>{t("terminal.attachedColumn")}</TableHead>
                  <TableHead>{t("terminal.created")}</TableHead>
                  <TableHead>{t("terminal.lastActivity")}</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(terminalSessions?.sessions ?? []).map((s) => (
                  <TableRow key={s.session_id}>
                    <TableCell className="font-mono text-xs">{s.session_id}</TableCell>
                    <TableCell>
                      <Badge variant={s.attached ? "success" : "outline"}>
                        {s.attached ? t("terminal.attached") : t("terminal.orphaned")}
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
                          aria-label={t("terminal.openNamed", { id: s.session_id })}
                          title={t("terminal.open")}
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
                          aria-label={t("terminal.killNamed", { id: s.session_id })}
                          title={t("terminal.killNamed", { id: s.session_id })}
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
                      {t("terminal.empty")}
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
              <h2 className="text-base font-semibold">{t("chatSessions.title")}</h2>
              {chatSessions && (
                <span className="text-xs text-muted-foreground">{t("chatSessions.trackedCount", { count: chatSessions.length })}</span>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setConfirmingResetAllStale(true)}
              disabled={staleChatSessions.length === 0 || resetAllStaleChatSessions.isPending}
              title={t("chatSessions.resetAllTitle")}
            >
              {resetAllStaleChatSessions.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RotateCcw className="h-4 w-4" />
              )}
              {t("chatSessions.resetAll", { count: staleChatSessions.length })}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t("chatSessions.description")}
          </p>
          {chatSessionsLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> {t("terminal.loading")}
            </div>
          )}
          {resetChatSession.isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {(resetChatSession.error as Error)?.message ?? t("chatSessions.resetFailed")}
            </div>
          )}
          <ConfirmDialog
            open={resettingChatSession !== null}
            title={t("chatSessions.resetTitle")}
            description={t("chatSessions.resetDescription")}
            confirmLabel={t("chatSessions.reset")}
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
              {(resetAllStaleChatSessions.error as Error)?.message ?? t("chatSessions.resetAllFailed")}
            </div>
          )}
          <ConfirmDialog
            open={confirmingResetAllStale}
            title={t("chatSessions.resetAllConfirm", { count: staleChatSessions.length })}
            description={t("chatSessions.resetAllDescription")}
            confirmLabel={t("chatSessions.resetAllAction")}
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
              {(deleteChatSession.error as Error)?.message ?? t("chatSessions.deleteFailed")}
            </div>
          )}
          <ConfirmDialog
            open={deletingChatSession !== null}
            title={t("chatSessions.deleteTitle")}
            description={t("chatSessions.deleteDescription", { title: deletingChatSession?.title ?? "" })}
            confirmLabel={t("chatSessions.delete")}
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
                  <TableHead>{t("chatSessions.agent")}</TableHead>
                  <TableHead>{t("terminal.session")}</TableHead>
                  <TableHead>{t("git.status")}</TableHead>
                  <TableHead>{t("terminal.lastActivity")}</TableHead>
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
                        {s.running ? t("chatSessions.running") : s.exists ? t("chatSessions.live") : t("chatSessions.stale")}
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
                          aria-label={t("chatSessions.openNamed", { title: s.session_title })}
                          title={t("terminal.open")}
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
                          aria-label={t("chatSessions.resetNamed", { title: s.session_title })}
                          title={t("chatSessions.resetHermes")}
                          onClick={() => setResettingChatSession({ sessionId: s.session_id, participantId: s.participant_id })}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          aria-label={t("chatSessions.deleteNamed", { title: s.session_title })}
                          title={t("chatSessions.delete")}
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
                      {t("chatSessions.empty")}
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
