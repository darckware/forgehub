import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/store/authStore";
import {
  useCreateDemand,
  useUpdateDemand,
  useUploadDemandAttachment,
  type Demand,
} from "@/hooks/useDemands";
import { useAgents } from "@/hooks/useAgent";
import { useTasks, type ProjectTask } from "@/hooks/useTask";

type OriginChoice = "none" | "task" | "demand";

/**
 * "Nova nota" / "Alterar" -- a side panel (not a modal), inline in the same
 * slot the reading pane normally occupies, per Marcelo's mailbox/internal-
 * email framing: composing or editing a message opens on the right, same
 * as reading one does. Handles both create (no `demand` prop) and edit
 * (prefilled from an existing `demand`) in one form, since the fields are
 * identical either way -- To (target agent), Origin (reply-to a Task or
 * another message, by its display number), Subject, Body, Attachments.
 *
 * `subject`/`body` stay controlled (lifted to DemandsPage) rather than
 * local state -- DemandsPage registers them as an AssistantForm while this
 * panel is open, so the assistant can fill them on request.
 */
export function DemandFormPanel({
  demand,
  subject,
  onSubjectChange,
  body,
  onBodyChange,
  onClose,
}: {
  /** Present in edit mode, undefined when composing a new message. */
  demand?: Demand;
  subject: string;
  onSubjectChange: (value: string) => void;
  body: string;
  onBodyChange: (value: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation("demands");
  const user = useAuthStore((s) => s.user);
  const { data: agents } = useAgents();
  // Origin "Task" resolves against ProjectTask.kanboard_task_id server-side
  // (demand.py's _resolve_origin) -- Kanboard assigns that number itself
  // when the task is created, so it's not something a person types from
  // memory. Picked by title instead; tasks never synced to Kanboard yet
  // (kanboard_task_id null) can't be an origin and are filtered out.
  const { data: allTasks, isLoading: tasksLoading } = useTasks();
  const kanboardTasks = (allTasks ?? []).filter(
    (t): t is ProjectTask & { kanboard_task_id: number } => t.kanboard_task_id != null
  );
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const createDemand = useCreateDemand();
  const updateDemand = useUpdateDemand();
  const uploadAttachment = useUploadDemandAttachment();
  const [error, setError] = useState<string | null>(null);

  const [targetAgentId, setTargetAgentId] = useState(demand?.target_agent_id ?? "");
  const [originChoice, setOriginChoice] = useState<OriginChoice>(
    demand?.origin_type === "task" ? "task" : demand?.origin_type === "demand" ? "demand" : "none"
  );
  const [originNumber, setOriginNumber] = useState("");

  const isEdit = demand !== undefined;
  const isPending = createDemand.isPending || updateDemand.isPending || uploadAttachment.isPending;
  const canSubmit = subject.trim().length > 0 && body.trim().length > 0 && !isPending;

  async function handleSubmit() {
    setError(null);
    const parsedOriginNumber = originChoice !== "none" && originNumber.trim() ? Number(originNumber) : undefined;
    if (originChoice !== "none" && parsedOriginNumber === undefined) {
      setError(t("form.originNumberRequired"));
      return;
    }
    try {
      if (isEdit) {
        await updateDemand.mutateAsync({
          id: demand.id,
          subject,
          body,
          targetAgentId: targetAgentId || null,
          originType: originChoice === "none" ? undefined : originChoice,
          originNumber: originChoice === "none" ? undefined : parsedOriginNumber,
        });
        for (const file of files) {
          await uploadAttachment.mutateAsync({ demandId: demand.id, file });
        }
      } else {
        const created = await createDemand.mutateAsync({
          from_agent: user?.username ?? "you",
          subject,
          body,
          targetAgentId: targetAgentId || undefined,
          originType: originChoice === "none" ? undefined : originChoice,
          originNumber: parsedOriginNumber,
        });
        for (const file of files) {
          await uploadAttachment.mutateAsync({ demandId: created.id, file });
        }
      }
      onClose();
    } catch (e) {
      setError((e as Error)?.message ?? "Failed to save");
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-l border-border/60">
      <div className="shrink-0 border-b border-border/60 px-5 py-4">
        <h2 className="text-base font-semibold">{isEdit ? t("editTitle") : t("newNoteTitle")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("newNoteDescription")}</p>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t("form.toAgent")}</label>
          <Select value={targetAgentId} onChange={(e) => setTargetAgentId(e.target.value)}>
            <option value="">{t("form.noAgent")}</option>
            {(agents ?? []).map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1 space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">{t("form.origin")}</label>
            <Select
              value={originChoice}
              onChange={(e) => {
                setOriginChoice(e.target.value as OriginChoice);
                setOriginNumber("");
              }}
            >
              <option value="none">{t("form.originNone")}</option>
              <option value="task">{t("form.originTask")}</option>
              <option value="demand">{t("form.originMessage")}</option>
            </Select>
          </div>
          {originChoice === "task" && (
            <div className="w-64 space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t("form.taskNumber")}</label>
              <Select value={originNumber} disabled={tasksLoading} onChange={(e) => setOriginNumber(e.target.value)}>
                <option value="">{tasksLoading ? t("form.taskLoading") : t("form.selectTask")}</option>
                {kanboardTasks.map((task) => (
                  <option key={task.id} value={task.kanboard_task_id}>
                    #{task.kanboard_task_id} — {task.title}
                  </option>
                ))}
              </Select>
            </div>
          )}
          {originChoice === "demand" && (
            <div className="w-28 space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t("form.messageNumber")}</label>
              <Input
                type="number"
                min={1}
                placeholder="#"
                value={originNumber}
                onChange={(e) => setOriginNumber(e.target.value)}
              />
            </div>
          )}
        </div>

        <Input
          placeholder={t("subjectPlaceholder")}
          value={subject}
          onChange={(e) => onSubjectChange(e.target.value)}
          maxLength={255}
        />
        <Textarea
          placeholder={t("bodyPlaceholder")}
          value={body}
          onChange={(e) => onBodyChange(e.target.value)}
          rows={12}
          className="font-mono text-sm"
        />

        <div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? []);
              setFiles((prev) => [...prev, ...picked]);
              e.target.value = "";
            }}
          />
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => fileInputRef.current?.click()}>
            <Paperclip className="h-3.5 w-3.5" /> {t("attachFileButton")}
          </Button>
          {files.length > 0 && (
            <ul className="mt-2 space-y-1">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1 text-xs">
                  <span className="truncate">{f.name}</span>
                  <button
                    type="button"
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      <div className="flex shrink-0 justify-end gap-3 border-t border-border/60 px-5 py-4">
        <Button variant="outline" onClick={onClose}>
          {t("cancel")}
        </Button>
        <Button disabled={!canSubmit} onClick={handleSubmit} className="min-w-[88px] gap-1.5">
          {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {t("send")}
        </Button>
      </div>
    </div>
  );
}
