import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Play, Radio, TestTube2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useProducts } from "@/hooks/useProduct";
import {
  useRunRoutineBackgroundTest,
  useWebAutomationRoutines,
  type AutomationTarget,
} from "@/hooks/useWorkspaceBrowser";

/**
 * `/testar` -- deterministic, client-intercepted local command (see
 * LOCAL_SLASH_COMMANDS in ChatPane.tsx). Dispatches straight to
 * `POST /routines/{id}:run-background` via apiClient/TanStack Query,
 * never through streamMessage/the Hermes session -- so it works even when
 * the `test_application` MCP tool isn't loaded in the agent's active
 * toolset (the known MCP-discovery bug this command exists to route
 * around, see the plan's "Risco explícito" section).
 */
export function TestApplicationDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("chat");
  const { data: products } = useProducts();
  const [productId, setProductId] = useState("");
  const [routineId, setRoutineId] = useState("");
  const [mode, setMode] = useState<"background" | "visible">("background");
  const [dispatched, setDispatched] = useState(false);

  const target: AutomationTarget | undefined = productId ? { type: "product", id: productId } : undefined;
  const routines = useWebAutomationRoutines(target);
  const dispatch = useRunRoutineBackgroundTest();

  if (!open) return null;

  function reset() {
    setProductId("");
    setRoutineId("");
    setMode("background");
    setDispatched(false);
    dispatch.reset();
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!routineId || !target) return;
    await dispatch.mutateAsync({ id: routineId, target, mode });
    setDispatched(true);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={handleClose} />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <form className="p-6" onSubmit={handleSubmit}>
          <div className="flex items-center gap-2">
            <TestTube2 className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">{t("testDialog.title")}</h2>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("testDialog.description")}</p>

          {dispatched ? (
            <div className="mt-4 rounded-md border border-border bg-muted/40 p-3 text-sm">
              {mode === "background" ? t("testDialog.dispatchedBackground") : t("testDialog.dispatchedVisible")}
            </div>
          ) : (
            <div className="mt-4 space-y-4">
              <div>
                <Label>{t("testDialog.fields.product")}</Label>
                <Select
                  value={productId}
                  onChange={(e) => {
                    setProductId(e.target.value);
                    setRoutineId("");
                  }}
                >
                  <option value="">{t("testDialog.fields.pickProduct")}</option>
                  {(products ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </Select>
              </div>

              {productId && (
                <div>
                  <Label>{t("testDialog.fields.routine")}</Label>
                  {routines.isLoading ? (
                    <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t("testDialog.loading")}
                    </p>
                  ) : (routines.data?.length ?? 0) === 0 ? (
                    <p className="mt-1 text-sm italic text-muted-foreground">{t("testDialog.noRoutines")}</p>
                  ) : (
                    <Select value={routineId} onChange={(e) => setRoutineId(e.target.value)}>
                      <option value="">{t("testDialog.fields.pickRoutine")}</option>
                      {(routines.data ?? []).map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                    </Select>
                  )}
                </div>
              )}

              {routineId && (
                <div>
                  <Label>{t("testDialog.fields.mode")}</Label>
                  <div className="mt-1.5 flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant={mode === "background" ? "default" : "outline"}
                      onClick={() => setMode("background")}
                      className="flex-1 gap-1.5"
                    >
                      <Radio className="h-3.5 w-3.5" />
                      {t("testDialog.modeBackground")}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={mode === "visible" ? "default" : "outline"}
                      onClick={() => setMode("visible")}
                      className="flex-1 gap-1.5"
                    >
                      <Play className="h-3.5 w-3.5" />
                      {t("testDialog.modeVisible")}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {dispatch.isError && (
            <p className="mt-3 text-sm text-destructive">{(dispatch.error as Error)?.message}</p>
          )}

          <div className="mt-6 flex justify-end gap-3">
            <Button type="button" variant="outline" onClick={handleClose}>
              {dispatched ? t("testDialog.buttons.close") : t("testDialog.buttons.cancel")}
            </Button>
            {!dispatched && (
              <Button type="submit" disabled={!routineId || dispatch.isPending} className="min-w-[100px] gap-1.5">
                {dispatch.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <TestTube2 className="h-3.5 w-3.5" />}
                {t("testDialog.buttons.run")}
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
