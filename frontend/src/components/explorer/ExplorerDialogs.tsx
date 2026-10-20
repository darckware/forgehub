import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslation } from "react-i18next";
import { Download, Loader2, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { isValidName, useExplorerFileContent } from "@/hooks/useFileExplorer";
import { errorMessage, type FileExplorerViewModel } from "@/hooks/useFileExplorerViewModel";
import { FolderPickerDialog } from "./FolderPickerDialog";
import type { QuickAccessItem } from "./ExplorerTree";

/** Every modal the Explorer can show, driven by `vm.dialog`. */
export function ExplorerDialogs({ vm, quickAccess }: { vm: FileExplorerViewModel; quickAccess: QuickAccessItem[] }) {
  const { t } = useTranslation("explorer");
  const dialog = vm.dialog;
  const working = vm.operation.status === "working";
  const error = vm.operation.status === "error" ? vm.operation.message ?? null : null;

  if (!dialog) return null;

  if (dialog.kind === "newFolder" || dialog.kind === "newFile" || dialog.kind === "rename") {
    const initial = dialog.kind === "rename" ? dialog.entry.name : dialog.kind === "newFolder" ? t("dialogs.defaultFolderName") : t("dialogs.defaultFileName");
    return (
      <NameDialog
        key={dialog.kind + (dialog.kind === "rename" ? dialog.entry.path : "")}
        title={
          dialog.kind === "rename"
            ? t("dialogs.renameTitle", { name: dialog.entry.name })
            : dialog.kind === "newFolder"
            ? t("dialogs.newFolderTitle")
            : t("dialogs.newFileTitle")
        }
        confirmLabel={dialog.kind === "rename" ? t("actions.rename") : t("actions.create")}
        initial={initial}
        // Like Explorer, a rename pre-selects the stem, not the extension.
        selectStem={dialog.kind === "rename" && dialog.entry.type === "file"}
        loading={working}
        error={error}
        onCancel={() => {
          vm.dismissError();
          vm.closeDialog();
        }}
        onSubmit={(name) =>
          dialog.kind === "rename" ? vm.rename(dialog.entry, name) : vm.createItem(dialog.kind, name)
        }
      />
    );
  }

  if (dialog.kind === "delete") {
    const count = dialog.entries.length;
    const folders = dialog.entries.filter((e) => e.type === "dir").length;
    return (
      <ConfirmDialog
        open
        title={count === 1 ? t("dialogs.deleteOneTitle", { name: dialog.entries[0].name }) : t("dialogs.deleteManyTitle", { count })}
        description={folders > 0 ? t("dialogs.deleteFoldersWarning") : t("dialogs.deleteWarning")}
        confirmLabel={t("actions.delete")}
        loading={working}
        error={error}
        onConfirm={() => void vm.removeEntries(dialog.entries)}
        onCancel={() => {
          vm.dismissError();
          vm.closeDialog();
        }}
      >
        {count > 1 && (
          <ul className="max-h-40 overflow-auto rounded-md border border-border bg-muted/30 p-2 font-mono text-xs">
            {dialog.entries.map((e) => (
              <li key={e.path} className="truncate">
                {e.type === "dir" ? `${e.name}/` : e.name}
              </li>
            ))}
          </ul>
        )}
      </ConfirmDialog>
    );
  }

  if (dialog.kind === "uploadConflict") {
    return (
      <ConfirmDialog
        open
        variant="default"
        icon="warning"
        title={t("dialogs.conflictTitle", { count: dialog.conflicts.length })}
        description={t("dialogs.conflictDescription")}
        confirmLabel={t("dialogs.replace")}
        onConfirm={() => void vm.startUpload(dialog.uploads, dialog.destination, true)}
        onCancel={vm.closeDialog}
      >
        <ul className="max-h-32 overflow-auto rounded-md border border-border bg-muted/30 p-2 font-mono text-xs">
          {dialog.conflicts.map((name) => (
            <li key={name} className="truncate">
              {name}
            </li>
          ))}
        </ul>
        <Button
          type="button"
          variant="secondary"
          className="mt-3 w-full"
          onClick={() => void vm.startUpload(dialog.uploads, dialog.destination, false)}
        >
          {t("dialogs.skipExisting")}
        </Button>
      </ConfirmDialog>
    );
  }

  if (dialog.kind === "transferTo") {
    return <FolderPickerDialog vm={vm} entries={dialog.entries} mode={dialog.mode} quickAccess={quickAccess} />;
  }

  if (dialog.kind === "edit") {
    return <EditorDialog path={dialog.path} vm={vm} />;
  }

  return (
    <Overlay title={dialog.entry.name} onClose={vm.closeDialog}>
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-[repeating-conic-gradient(hsl(var(--muted))_0%_25%,transparent_0%_50%)] bg-[length:20px_20px] p-4">
        <img src={dialog.url} alt={dialog.entry.name} className="max-h-full max-w-full object-contain" />
      </div>
      <div className="flex justify-end border-t border-border p-3">
        <Button variant="outline" size="sm" onClick={() => void vm.download([dialog.entry])}>
          <Download className="mr-1.5 h-4 w-4" />
          {t("actions.download")}
        </Button>
      </div>
    </Overlay>
  );
}

const nameSchema = z.object({
  name: z.string().trim().min(1, "required").refine(isValidName, "invalid"),
});

function NameDialog({
  title,
  confirmLabel,
  initial,
  selectStem,
  loading,
  error,
  onCancel,
  onSubmit,
}: {
  title: string;
  confirmLabel: string;
  initial: string;
  selectStem: boolean;
  loading: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (name: string) => Promise<boolean>;
}) {
  const { t } = useTranslation("explorer");
  const form = useForm<z.infer<typeof nameSchema>>({ resolver: zodResolver(nameSchema), defaultValues: { name: initial } });
  const inputRef = useRef<HTMLInputElement | null>(null);
  const { ref: registerRef, ...field } = form.register("name");

  useEffect(() => {
    // ConfirmDialog focuses its Cancel button on open; take focus after it.
    const timer = setTimeout(() => {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      const dot = initial.lastIndexOf(".");
      input.setSelectionRange(0, selectStem && dot > 0 ? dot : initial.length);
    }, 0);
    return () => clearTimeout(timer);
  }, [initial, selectStem]);

  const submit = form.handleSubmit(async ({ name }) => {
    await onSubmit(name);
  });
  const fieldError = form.formState.errors.name?.message;

  return (
    <ConfirmDialog
      open
      variant="default"
      icon="wrench"
      title={title}
      confirmLabel={confirmLabel}
      loading={loading}
      error={error}
      onConfirm={() => void submit()}
      onCancel={onCancel}
    >
      <form onSubmit={(e) => void submit(e)}>
        <Input
          {...field}
          ref={(el) => {
            registerRef(el);
            inputRef.current = el;
          }}
          aria-invalid={Boolean(fieldError)}
          aria-label={t("dialogs.nameLabel")}
          autoComplete="off"
          spellCheck={false}
        />
        {fieldError && (
          <p className="mt-1.5 text-xs text-destructive">
            {fieldError === "required" ? t("dialogs.nameRequired") : t("dialogs.nameInvalid")}
          </p>
        )}
      </form>
    </ConfirmDialog>
  );
}

function EditorDialog({ path, vm }: { path: string; vm: FileExplorerViewModel }) {
  const { t } = useTranslation("explorer");
  const content = useExplorerFileContent(path);
  const [draft, setDraft] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const value = draft ?? content.data?.content ?? "";
  const dirty = draft !== null && draft !== content.data?.content;
  const saving = vm.operation.status === "working";

  async function save() {
    if (!dirty || draft === null) return;
    const ok = await vm.saveContent(path, draft);
    if (ok) {
      await content.refetch();
      setDraft(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    }
  }

  function close() {
    if (dirty && !window.confirm(t("editor.discardChanges"))) return;
    vm.dismissError();
    vm.closeDialog();
  }

  return (
    <Overlay title={path} onClose={close}>
      {content.isLoading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : content.isError ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm text-muted-foreground">
          <p>{errorMessage(content.error)}</p>
          <Button variant="outline" size="sm" onClick={() => void vm.download([{ name: path.split("/").pop() ?? "file", path, type: "file", size: null, modified: null, is_symlink: false }])}>
            <Download className="mr-1.5 h-4 w-4" />
            {t("actions.download")}
          </Button>
        </div>
      ) : (
        <Textarea
          value={value}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
              e.preventDefault();
              void save();
            }
          }}
          spellCheck={false}
          className="min-h-0 flex-1 resize-none rounded-none border-0 font-mono text-xs leading-relaxed focus-visible:ring-0"
          aria-label={t("editor.contentLabel")}
        />
      )}
      <div className="flex items-center justify-between gap-2 border-t border-border p-3">
        <span className="truncate text-xs text-destructive">{vm.operation.status === "error" ? vm.operation.message : ""}</span>
        <div className="flex shrink-0 items-center gap-2">
          {dirty && <span className="text-xs text-muted-foreground">{t("editor.unsaved")}</span>}
          {saved && <span className="text-xs text-green-500">{t("editor.saved")}</span>}
          <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
            {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Save className="mr-1.5 h-4 w-4" />}
            {t("actions.save")}
          </Button>
        </div>
      </div>
    </Overlay>
  );
}

function Overlay({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const { t } = useTranslation("explorer");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" aria-hidden="true" onMouseDown={onClose} />
      <div className="relative z-10 flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
          <span className="truncate font-mono text-xs text-muted-foreground" title={title}>
            {title}
          </span>
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t("actions.close")} onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        {children}
      </div>
    </div>,
    document.body
  );
}
