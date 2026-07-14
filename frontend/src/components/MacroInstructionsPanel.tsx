import { useState } from "react";
import { Bot, Send, Wand2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgents } from "@/hooks/useAgent";
import { useAssistantStore } from "@/store/assistantStore";

/** Builds the Assistant composer draft from the user's free-text lines --
 * numbered so the agent works through them one at a time and reports each
 * result, per docs/MANUAL.md's Assistant Policy (explicit instruction from
 * the composer, on the shared Workspace browser session). */
function buildMacroMessage(productName: string, lines: string[]): string {
  const steps = lines.map((line, index) => `${index + 1}. ${line}`).join("\n");
  return [
    `Execute estas instruções na sessão do navegador compartilhado do Workspace (o app aberto agora é "${productName}"), uma de cada vez.`,
    "Confirme o resultado de cada passo antes de seguir para o próximo e pare para relatar se algum falhar.",
    "",
    steps,
  ].join("\n");
}

export function MacroInstructionsPanel({ productName, onClose }: { productName: string; onClose: () => void }) {
  const [text, setText] = useState("");
  const { data: agents } = useAgents();
  const setAssistantOpen = useAssistantStore((s) => s.setOpen);
  const setPendingSeed = useAssistantStore((s) => s.setPendingSeed);
  const setPendingAgentId = useAssistantStore((s) => s.setPendingAgentId);

  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);

  function send() {
    if (lines.length === 0) return;
    const athos = agents?.find((agent) => agent.name.trim().toLowerCase() === "athos");
    setPendingSeed(buildMacroMessage(productName, lines));
    setPendingAgentId(athos?.id ?? null);
    setAssistantOpen(true);
    onClose();
  }

  return (
    <div className="absolute inset-y-2 right-2 z-20 flex w-[min(520px,calc(100%-1rem))] flex-col rounded-lg border border-border bg-background shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="flex items-center gap-2 font-semibold"><Wand2 className="h-4 w-4" /> Macro</p>
          <p className="text-xs text-muted-foreground">{productName}</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
        <p className="text-xs text-muted-foreground">
          Uma instrução por linha, em linguagem natural (ex.: "clique em Update do Codex"). O Athos recebe a lista
          pronta no composer do Assistente e interage sozinho com esta mesma sessão de navegador — você ainda precisa
          apertar Enviar lá para confirmar.
        </p>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={"Clique em Update do Codex\nEspere a versão instalada mudar\nTire um print do resultado"}
          spellCheck={false}
          className="h-full min-h-[220px] flex-1 resize-none rounded-md border border-input bg-background p-2 font-mono text-xs outline-none focus:ring-1 focus:ring-ring"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted-foreground">{lines.length} instruction(s)</span>
          <Button size="sm" disabled={lines.length === 0} onClick={send}>
            <Bot className="mr-1.5 h-3.5 w-3.5" /> Send to Athos <Send className="ml-1.5 h-3 w-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}
