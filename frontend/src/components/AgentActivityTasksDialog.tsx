import { useTranslation } from "react-i18next";
import { CheckCircle2, Folder, Loader2, Send, X, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ActivityTask } from "@/hooks/useAgentActivityViewModel";

const STATUS_META: Record<
  NonNullable<ActivityTask["status"]>,
  { icon: typeof Loader2; badge: "default" | "warning" | "success" | "destructive"; spin?: boolean }
> = {
  dispatched: { icon: Send, badge: "default" },
  running: { icon: Loader2, badge: "warning", spin: true },
  completed: { icon: CheckCircle2, badge: "success" },
  failed: { icon: XCircle, badge: "destructive" },
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}

/** Follows the ImprovePromptDialog pattern (hand-rolled fixed overlay, no
 * generic shadcn Dialog primitive exists in this codebase yet) -- lists the
 * same tasks the board's packets/glows represent, as plain text/status rows
 * so the operator can read subject + result without hovering nodes. */
export function AgentActivityTasksDialog({ tasks, onClose }: { tasks: ActivityTask[]; onClose: () => void }) {
  const { t } = useTranslation("agentActivity");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <Card
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <h2 className="text-sm font-semibold">{t("dialog.title")}</h2>
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {tasks.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">{t("dialog.empty")}</p>
          )}
          {tasks.map((task) => {
            const meta = task.status ? STATUS_META[task.status] : null;
            const Icon = meta?.icon ?? Send;
            return (
              <div key={task.id} className="rounded-lg border border-border/60 p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      #{task.number} {task.subject}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {task.fromLabel} → {task.toLabel} · {formatTime(task.updatedAt)}
                      {task.projectName && ` · ${task.projectName}`}
                    </p>
                    {task.workingPath && (
                      <p className="mt-0.5 flex items-center gap-1 truncate font-mono text-[10px] text-muted-foreground/80">
                        <Folder className="h-2.5 w-2.5 shrink-0" />
                        {task.workingPath}
                      </p>
                    )}
                  </div>
                  {meta && (
                    <Badge variant={meta.badge} className="flex shrink-0 items-center gap-1">
                      <Icon className={cn("h-3 w-3", meta.spin && "animate-spin")} />
                      {t(`dialog.status.${task.status}`)}
                    </Badge>
                  )}
                </div>
                {task.resultPreview && (
                  <p className="mt-2 line-clamp-3 rounded bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
                    {task.resultPreview}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
