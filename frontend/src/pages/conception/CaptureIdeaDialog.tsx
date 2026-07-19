import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateIdea } from "@/hooks/useSystemScope";

const EMPTY_FORM = { name: "", problem_statement: "", vision: "", scope_summary: "", requested_by: "", priority: "medium" };

/** "+ New idea" -- was previously a permanently-open form filling the whole
 * left column of the Conception page, pushing the actually-used
 * "Development requests" list into a cramped narrow column. Same
 * open/onClose modal shell as ComposeDemandDialog.tsx (Inbox's "New note"). */
export function CaptureIdeaDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("conception");
  const create = useCreateIdea();
  const [form, setForm] = useState(EMPTY_FORM);

  if (!open) return null;

  function reset() {
    setForm(EMPTY_FORM);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await create.mutateAsync(form);
    reset();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => { reset(); onClose(); }}
      />
      <div className="relative z-10 w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <form className="p-6" onSubmit={handleSubmit}>
          <h2 className="text-base font-semibold">{t("captureIdea.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("captureIdea.description")}
          </p>

          <div className="mt-4 space-y-4">
            <div><Label>{t("captureIdea.fields.name")}</Label><Input required value={form.name} onChange={e => setForm({...form, name:e.target.value})}/></div>
            <div><Label>{t("captureIdea.fields.problemStatement")}</Label><Textarea required rows={4} value={form.problem_statement} onChange={e => setForm({...form, problem_statement:e.target.value})}/></div>
            <div><Label>{t("captureIdea.fields.vision")}</Label><Textarea rows={3} value={form.vision} onChange={e => setForm({...form, vision:e.target.value})}/></div>
            <div><Label>{t("captureIdea.fields.initialScope")}</Label><Textarea rows={3} value={form.scope_summary} onChange={e => setForm({...form, scope_summary:e.target.value})}/></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{t("captureIdea.fields.priority")}</Label>
                <Select value={form.priority} onChange={e => setForm({...form, priority: e.target.value})}>
                  <option value="low">{t("captureIdea.priorityOptions.low")}</option>
                  <option value="medium">{t("captureIdea.priorityOptions.medium")}</option>
                  <option value="high">{t("captureIdea.priorityOptions.high")}</option>
                  <option value="critical">{t("captureIdea.priorityOptions.critical")}</option>
                </Select>
              </div>
              <div><Label>{t("captureIdea.fields.requestedBy")}</Label><Input value={form.requested_by} onChange={e => setForm({...form, requested_by:e.target.value})}/></div>
            </div>
          </div>

          {create.isError && (
            <p className="mt-3 text-sm text-destructive">{(create.error as Error)?.message}</p>
          )}

          <div className="mt-6 flex justify-end gap-3">
            <Button type="button" variant="outline" onClick={() => { reset(); onClose(); }}>
              {t("captureIdea.buttons.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending} className="min-w-[88px] gap-1.5">
              {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              {t("captureIdea.buttons.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
