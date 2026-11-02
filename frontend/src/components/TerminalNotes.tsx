import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useUpdateTerminalMetadata } from "@/hooks/useTerminalBrowse";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";

export function TerminalNotes({ sessionId, notes, open, onClose }: { sessionId: string; notes: string; open: boolean; onClose: () => void }) {
  const { t } = useTranslation("workspace");
  const [draft, setDraft] = useState(notes);
  const [base, setBase] = useState(notes);
  const save = useUpdateTerminalMetadata();
  useEffect(() => {
    if (draft === base && notes !== base) { setDraft(notes); setBase(notes); }
  }, [notes, base, draft]);
  const dirty = draft !== base;
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  return (
    <aside aria-label={t("terminalNotes.title")} className={cn("h-full w-80 max-w-[45%] shrink-0 flex-col gap-3 border-l border-border bg-card p-3 max-md:absolute max-md:inset-y-0 max-md:right-0 max-md:z-10 max-md:w-[85%] max-md:max-w-none", open ? "flex" : "hidden")}>
      <div className="flex items-center justify-between gap-2"><h2 className="font-medium">{t("terminalNotes.title")}</h2><Button variant="ghost" size="sm" onClick={onClose}>{t("terminalNotes.close")}</Button></div>
      <label htmlFor={`notes-${sessionId}`} className="text-sm text-muted-foreground">{t("terminalNotes.description")}</label>
      <textarea id={`notes-${sessionId}`} value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={20000} className="min-h-40 flex-1 resize-none rounded-md border border-input bg-background p-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring" />
      {notes !== base && dirty && <p role="alert" className="text-sm text-destructive">{t("terminalNotes.conflict")}</p>}
      {save.isError && <p role="alert" className="text-sm text-destructive">{t(save.error instanceof ApiError && save.error.status === 409 ? "terminalNotes.conflict" : "terminalNotes.error")}</p>}
      <Button disabled={!dirty || save.isPending || notes !== base} onClick={async () => { try { const result = await save.mutateAsync({ id: sessionId, notes: draft, expected_notes: base }); setBase(result.notes); } catch { /* Keep the draft for retry. */ } }}>{save.isPending ? t("terminalNotes.saving") : t("terminalNotes.save")}</Button>
    </aside>
  );
}
