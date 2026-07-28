import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, ChevronDown, ChevronRight, Loader2, Play, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useProducts } from "@/hooks/useProduct";
import {
  useRunRoutineBackgroundTest,
  useTestRuns,
  useToggleRoutineBackgroundTest,
  useWebAutomationRoutines,
  type AutomationTarget,
  type WebAutomationTestRun,
} from "@/hooks/useWorkspaceBrowser";

/**
 * "Background tests" tab of the Systems Hub -- pick a product, toggle which
 * of its existing routines (created via the Web App pane's Automations
 * panel -- this tab is deliberately read-only for routine CRUD) are
 * background-testable, dispatch a run in either mode, and watch the shared
 * history. See the plan's Fase 3/Fase 4.
 */

const STATUS_BADGE: Record<WebAutomationTestRun["status"], { variant: "outline" | "success" | "destructive"; icon: typeof Loader2 }> = {
  queued: { variant: "outline", icon: Loader2 },
  running: { variant: "outline", icon: Loader2 },
  passed: { variant: "success", icon: CheckCircle2 },
  failed: { variant: "destructive", icon: AlertCircle },
  error: { variant: "destructive", icon: AlertCircle },
};

function TestRunRow({ run }: { run: WebAutomationTestRun }) {
  const { t } = useTranslation("systemsHub");
  const [expanded, setExpanded] = useState(false);
  const badge = STATUS_BADGE[run.status];
  const Icon = badge.icon;
  const spinning = run.status === "queued" || run.status === "running";

  return (
    <li className="rounded-md border">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-2.5 text-left text-sm"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex min-w-0 items-center gap-2">
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
          <Badge variant={badge.variant} className="gap-1">
            <Icon className={`h-3 w-3 ${spinning ? "animate-spin" : ""}`} />
            {t(`backgroundTests.status.${run.status}`)}
          </Badge>
          <Badge variant="outline" className="gap-1">
            {run.mode === "background" ? <Radio className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {t(`backgroundTests.mode.${run.mode}`)}
          </Badge>
          <span className="truncate text-xs text-muted-foreground">
            {run.started_at ? new Date(run.started_at).toLocaleString() : new Date(run.created_at).toLocaleString()}
          </span>
        </div>
      </button>
      {expanded && (
        <div className="space-y-2 border-t p-2.5">
          {run.report && (
            <pre className="whitespace-pre-wrap rounded-md bg-muted/40 p-2 font-mono text-xs">{run.report}</pre>
          )}
          {run.error && <p className="text-xs text-destructive">{run.error}</p>}
          {run.screenshot_paths && run.screenshot_paths.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {t("backgroundTests.screenshotCount", { count: run.screenshot_paths.length })}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export function BackgroundTestsPanel() {
  const { t } = useTranslation("systemsHub");
  const { data: products } = useProducts();
  const [selectedProductId, setSelectedProductId] = useState("");
  const target: AutomationTarget | undefined = selectedProductId ? { type: "product", id: selectedProductId } : undefined;

  const routines = useWebAutomationRoutines(target);
  const testRuns = useTestRuns(target);
  const toggle = useToggleRoutineBackgroundTest();
  const dispatch = useRunRoutineBackgroundTest();

  return (
    <div className="space-y-4">
      <select
        value={selectedProductId}
        onChange={(e) => setSelectedProductId(e.target.value)}
        className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
      >
        <option value="">{t("backgroundTests.pickProduct")}</option>
        {(products ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>

      {target && (
        <>
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("backgroundTests.routinesTitle")}</p>
            {routines.isLoading && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> {t("backgroundTests.loading")}
              </p>
            )}
            {!routines.isLoading && (routines.data?.length ?? 0) === 0 && (
              <p className="rounded-md border border-dashed p-4 text-center text-sm italic text-muted-foreground">
                {t("backgroundTests.noRoutines")}
              </p>
            )}
            <ul className="space-y-2">
              {(routines.data ?? []).map((routine) => (
                <li key={routine.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{routine.name}</p>
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={routine.background_test_enabled}
                        onChange={(e) =>
                          toggle.mutate({ id: routine.id, target, enabled: e.target.checked })
                        }
                        className="h-3.5 w-3.5 rounded border-input"
                      />
                      {t("backgroundTests.enableToggle")}
                    </label>
                  </div>
                  {routine.background_test_enabled && (
                    <div className="flex shrink-0 gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={dispatch.isPending}
                        onClick={() => dispatch.mutate({ id: routine.id, target, mode: "background" })}
                      >
                        <Radio className="mr-1.5 h-3.5 w-3.5" />
                        {t("backgroundTests.runBackground")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={dispatch.isPending}
                        onClick={() => dispatch.mutate({ id: routine.id, target, mode: "visible" })}
                      >
                        <Play className="mr-1.5 h-3.5 w-3.5" />
                        {t("backgroundTests.runVisible")}
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("backgroundTests.historyTitle")}</p>
            {(testRuns.data?.length ?? 0) === 0 && (
              <p className="rounded-md border border-dashed p-4 text-center text-sm italic text-muted-foreground">
                {t("backgroundTests.noHistory")}
              </p>
            )}
            <ul className="space-y-1.5">
              {(testRuns.data ?? []).map((run) => (
                <TestRunRow key={run.id} run={run} />
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
