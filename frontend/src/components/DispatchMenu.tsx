import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { Demand } from "@/hooks/useDemands";
import { useAgents } from "@/hooks/useAgent";

const REPLY_TO_SENDER = "__reply_to_sender__";

/**
 * "Dispatch to agent" -- sends demand.body (+ an optional command
 * instruction) as a prompt to a target agent's CLI, via
 * POST /demands/{id}/dispatch. Sibling of ConvertMenu, same visual pattern
 * (inline expanding bar, not a popover), but a different action: this one
 * actually runs the target agent instead of filing the note elsewhere.
 */
export function DispatchMenu({
  demand,
  onDispatch,
  isPending,
  error,
}: {
  demand: Demand;
  onDispatch: (payload: { targetAgentId?: string; replyToSender?: boolean; commandText?: string }) => void;
  isPending: boolean;
  error?: string | null;
}) {
  const { t } = useTranslation("demands");
  const { data: agents, isLoading: agentsLoading } = useAgents();
  const dispatchable = (agents ?? []).filter((a) => a.runtime_type);
  const canReplyToSender = Boolean(demand.from_agent_id);

  const [selection, setSelection] = useState<string>("");
  const [commandText, setCommandText] = useState("");

  // Only require a command when the item has no prior direction of its
  // own -- a fresh note with no origin (Marcelo composing from scratch or
  // forwarding an unrelated note), per PROPOSTA §3.1. A reply continuing an
  // existing thread already carries its own direction in the body.
  const needsCommand = demand.origin_id === null;

  useEffect(() => {
    if (!selection && canReplyToSender) setSelection(REPLY_TO_SENDER);
  }, [canReplyToSender, selection]);

  function handleSubmit() {
    if (!selection) return;
    onDispatch({
      targetAgentId: selection === REPLY_TO_SENDER ? undefined : selection,
      replyToSender: selection === REPLY_TO_SENDER,
      commandText: commandText.trim() || undefined,
    });
  }

  const canSubmit = Boolean(selection) && (!needsCommand || Boolean(commandText.trim()));

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Send className="h-3.5 w-3.5" /> {t("dispatch.title")}
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Select
          value={selection}
          className="h-8 w-56 text-xs"
          disabled={agentsLoading}
          onChange={(e) => setSelection(e.target.value)}
        >
          <option value="">{agentsLoading ? t("dispatch.loading") : t("dispatch.selectAgent")}</option>
          {canReplyToSender && <option value={REPLY_TO_SENDER}>{t("dispatch.replyToSender")}</option>}
          {dispatchable.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </Select>
        <Button size="sm" disabled={!canSubmit || isPending} onClick={handleSubmit}>
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("dispatch.submit")}
        </Button>
      </div>
      {needsCommand && (
        <Textarea
          value={commandText}
          onChange={(e) => setCommandText(e.target.value)}
          placeholder={t("dispatch.commandPlaceholder")}
          className="min-h-16 text-xs"
        />
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
