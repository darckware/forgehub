import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Loader2, Pencil, Plus, Save, Send, Trash2, Wand2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAgents } from "@/hooks/useAgent";
import {
  type AutomationTarget,
  type MacroInstructionSet,
  useCreateMacroInstructionSet,
  useDeleteMacroInstructionSet,
  useMacroInstructionSets,
  useUpdateMacroInstructionSet,
} from "@/hooks/useWorkspaceBrowser";
import { useAssistantStore } from "@/store/assistantStore";

/** Builds the Assistant composer draft from a macro's saved lines --
 * numbered so the agent works through them one at a time and reports each
 * result, per docs/MANUAL.md's Assistant Policy (explicit instruction from
 * the composer, on the shared Workspace browser session). */
function buildMacroMessage(targetName: string, lines: string[]): string {
  const steps = lines.map((line, index) => `${index + 1}. ${line}`).join("\n");
  return [
    `Execute estas instruções na sessão do navegador compartilhado do Workspace (o app aberto agora é "${targetName}"), uma de cada vez.`,
    "Confirme o resultado de cada passo antes de seguir para o próximo e pare para relatar se algum falhar.",
    "",
    steps,
  ].join("\n");
}

export function MacroInstructionsPanel({ target, targetName, onClose }: { target: AutomationTarget; targetName: string; onClose: () => void }) {
  const { t } = useTranslation("workspace");
  const macros = useMacroInstructionSets(target);
  const create = useCreateMacroInstructionSet();
  const update = useUpdateMacroInstructionSet();
  const remove = useDeleteMacroInstructionSet();
  const { data: agents } = useAgents();
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingSeed = useAssistantStore((s) => s.setPendingSeed);
  const setPendingAgentId = useAssistantStore((s) => s.setPendingAgentId);

  const [editing, setEditing] = useState<MacroInstructionSet | "new" | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [text, setText] = useState("");

  useEffect(() => {
    if (!editing) return;
    setName(editing === "new" ? "" : editing.name);
    setDescription(editing === "new" ? "" : editing.description ?? "");
    setText(editing === "new" ? "" : editing.lines.join("\n"));
  }, [editing]);

  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const saving = create.isPending || update.isPending;
  const mutationError = create.error ?? update.error ?? remove.error;

  function save() {
    if (!name.trim() || lines.length === 0) return;
    const payload = { target, name: name.trim(), description: description.trim() || undefined, lines };
    if (editing === "new") create.mutate(payload, { onSuccess: () => setEditing(null) });
    else if (editing) update.mutate({ id: editing.id, ...payload }, { onSuccess: () => setEditing(null) });
  }

  function sendToAthos(macro: MacroInstructionSet) {
    const athos = agents?.find((agent) => agent.name.trim().toLowerCase() === "athos");
    setPendingSeed(buildMacroMessage(targetName, macro.lines));
    setPendingAgentId(athos?.id ?? null);
    setAssistantOpen(true);
    onClose();
  }

  return (
    <div className="absolute inset-y-2 right-2 z-20 flex w-[min(560px,calc(100%-1rem))] flex-col rounded-lg border border-border bg-background shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="flex items-center gap-2 font-semibold"><Wand2 className="h-4 w-4" /> {t("macroPanel.title")}</p>
          <p className="text-xs text-muted-foreground">{targetName}</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <Input placeholder={t("macroPanel.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
              <Input placeholder={t("macroPanel.descriptionPlaceholder")} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div>
              <p className="mb-1 text-xs text-muted-foreground">{t("macroPanel.helpText")}</p>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder={t("macroPanel.linesPlaceholder")}
                spellCheck={false}
                className="h-full min-h-[180px] w-full resize-none rounded-md border border-input bg-background p-2 font-mono text-xs outline-none focus:ring-1 focus:ring-ring"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={save} disabled={!name.trim() || lines.length === 0 || saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}{t("macroPanel.saveMacro")}
              </Button>
              <Button variant="outline" onClick={() => setEditing(null)}>{t("macroPanel.cancel")}</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <Button size="sm" onClick={() => setEditing("new")}><Plus className="mr-2 h-4 w-4" /> {t("macroPanel.newMacro")}</Button>
            {macros.isLoading && <p className="text-sm text-muted-foreground"><Loader2 className="mr-2 inline h-4 w-4 animate-spin" />{t("macroPanel.loadingMacros")}</p>}
            {!macros.isLoading && (macros.data?.length ?? 0) === 0 && (
              <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">{t("macroPanel.noMacrosForTarget")}</p>
            )}
            {macros.data?.map((macro) => (
              <div key={macro.id} className="flex items-center gap-3 rounded-md border p-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{macro.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{macro.description || t("macroPanel.instructionCount", { count: macro.lines.length })}</p>
                </div>
                <Button size="sm" onClick={() => sendToAthos(macro)}>
                  <Bot className="mr-1.5 h-3.5 w-3.5" /> {t("macroPanel.send")} <Send className="ml-1.5 h-3 w-3" />
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setEditing(macro)}><Pencil className="h-4 w-4" /></Button>
                <Button variant="ghost" size="icon" onClick={() => remove.mutate({ id: macro.id, target })}><Trash2 className="h-4 w-4 text-destructive" /></Button>
              </div>
            ))}
          </div>
        )}
        {mutationError && <p className="mt-3 text-sm text-destructive">{mutationError.message}</p>}
      </div>
    </div>
  );
}
