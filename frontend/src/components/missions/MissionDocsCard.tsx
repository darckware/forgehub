import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Folder, FolderOpen, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FileExplorerPane } from "@/components/explorer/FileExplorerPane";
import { useExplorerListing, useExplorerMutations } from "@/hooks/useFileExplorer";
import { ApiError } from "@/lib/api";

/** The mission's study material (2026-11-12, Marcelo: "deixo na pasta docs do
 * projeto todas as documentações para os agentes estudarem"): what is in
 * <working dir>/docs/, plus a button that opens the Explorer right there
 * (creating docs/ first when it doesn't exist) to upload or organize files.
 * Admin-only, like the Explorer itself. */
export function MissionDocsCard({ workingDirectory }: { workingDirectory: string | null | undefined }) {
  const { t } = useTranslation("missions");
  const root = workingDirectory?.trim().replace(/\/+$/, "") ?? "";
  const docsPath = root ? `${root}/docs` : "";
  const listing = useExplorerListing(docsPath, Boolean(docsPath));
  const { createFolder } = useExplorerMutations();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = listing.error instanceof ApiError && listing.error.status === 404;
  const entries = (listing.data?.path === docsPath ? listing.data.entries : []).filter((e) => !e.name.startsWith("."));

  async function openExplorer() {
    setError(null);
    if (missing) {
      try {
        await createFolder.mutateAsync(docsPath);
      } catch (err) {
        if (!(err instanceof ApiError && err.status === 409)) {
          setError(t("docs.createError"));
          return;
        }
      }
    }
    setOpen(true);
  }

  return (
    <section className="space-y-3 rounded-xl border p-4 sm:p-6" data-testid="mission-docs">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{t("docs.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("docs.description")}</p>
          {docsPath && <p className="font-mono text-xs text-muted-foreground [overflow-wrap:anywhere]">{docsPath}/</p>}
        </div>
        {docsPath && (
          <Button variant="outline" className="shrink-0" onClick={() => void openExplorer()} disabled={createFolder.isPending}>
            {createFolder.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FolderOpen className="mr-2 h-4 w-4" />}
            {t("docs.openExplorer")}
          </Button>
        )}
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {!docsPath ? (
        <p role="status" className="text-sm text-amber-600 dark:text-amber-400">{t("docs.noWorkingDirectory")}</p>
      ) : listing.isLoading ? (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{t("docs.loading")}</p>
      ) : missing ? (
        <p role="status" className="text-sm text-amber-600 dark:text-amber-400">{t("docs.missing")}</p>
      ) : listing.isError ? (
        <p role="alert" className="text-sm text-destructive">{t("docs.loadError")}</p>
      ) : entries.length === 0 ? (
        <p role="status" className="text-sm text-amber-600 dark:text-amber-400">{t("docs.empty")}</p>
      ) : (
        <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {entries.map((e) => (
            <li key={e.path} className="flex min-w-0 items-center gap-2 text-sm">
              {e.type === "dir" ? <Folder className="h-4 w-4 shrink-0 text-muted-foreground" /> : <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />}
              <span className="truncate">{e.name}{e.type === "dir" ? "/" : ""}</span>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-label={t("docs.explorerTitle")}>
          <div className="fixed inset-0 bg-black/60" onClick={() => { setOpen(false); void listing.refetch(); }} />
          <div className="relative my-auto flex h-[85vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border bg-background shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-2">
              <span className="truncate text-sm font-medium">{t("docs.explorerTitle")} · {docsPath}/</span>
              <Button variant="ghost" size="icon" aria-label={t("docs.close")} onClick={() => { setOpen(false); void listing.refetch(); }}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="relative min-h-0 flex-1">
              <FileExplorerPane initialPath={docsPath} active quickAccess={[{ label: t("docs.title"), path: docsPath, icon: "star" }, { label: root.split("/").pop() || root, path: root, icon: "folder" }]} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
