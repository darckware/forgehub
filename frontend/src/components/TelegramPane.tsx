import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, RefreshCw, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  type Agent,
  useAgentsTelegramStatus,
  useAgentTelegramConversation,
  useSendAgentTelegramMessage,
} from "@/hooks/useAgent";
import { cn } from "@/lib/utils";

interface TelegramPaneProps {
  agentId: string;
  agents: Agent[];
  active: boolean;
  onAgentChange: (agentId: string) => void;
}

export function TelegramPane({ agentId, agents, active, onAgentChange }: TelegramPaneProps) {
  const [draft, setDraft] = useState("");
  const [deliveryWarning, setDeliveryWarning] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const conversation = useAgentTelegramConversation(agentId, active);
  const sendMessage = useSendAgentTelegramMessage(agentId);
  const { data: statuses } = useAgentsTelegramStatus();
  const agent = agents.find((item) => item.id === agentId);
  const status = statuses?.agents.find((item) => item.agent_id === agentId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.data?.messages.length]);

  async function submit() {
    const message = draft.trim();
    if (!message || sendMessage.isPending) return;
    setDraft("");
    setDeliveryWarning(null);
    try {
      const result = await sendMessage.mutateAsync(message);
      setDeliveryWarning(result.delivery_error ?? null);
    } catch {
      setDraft(message);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void submit();
  }

  return (
    <section
      className="flex h-full min-h-0 flex-col bg-background"
      aria-label={`Telegram de ${agent?.name ?? "agente"}`}
    >
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Send className="h-4 w-4 text-sky-500" />
        <select
          className="h-8 min-w-40 rounded-md border border-input bg-background px-2 text-sm"
          value={agentId}
          onChange={(event) => onAgentChange(event.target.value)}
          aria-label="Agente do canal Telegram"
        >
          {agents.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <span className={cn(
          "rounded-full px-2 py-0.5 text-xs",
          status?.status === "ok" ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground",
        )}>
          {status?.status === "ok" ? "canal ativo" : status?.status === "not_running" ? "gateway parado" : "não configurado"}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="ml-auto h-8 w-8"
          onClick={() => void conversation.refetch()}
          disabled={conversation.isFetching}
          title="Atualizar mensagens"
        >
          <RefreshCw className={cn("h-4 w-4", conversation.isFetching && "animate-spin")} />
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {conversation.isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : conversation.isError ? (
          <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">Não foi possível carregar o histórico do Telegram.</p>
        ) : conversation.data?.messages.length ? (
          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            {conversation.data.messages.map((message) => (
              <article
                key={message.id}
                className={cn(
                  "max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm",
                  message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "mr-auto bg-muted",
                )}
              >
                <div className="mb-1 text-[10px] opacity-70">
                  {message.role === "user" ? "Você · Telegram" : agent?.name ?? "Agente"}
                  {" · "}{new Date(message.timestamp * 1000).toLocaleString()}
                </div>
                {message.content}
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
            <div>
              <Send className="mx-auto mb-2 h-8 w-8" />
              <p>Nenhuma conversa do Telegram encontrada para {agent?.name ?? "este agente"}.</p>
              <p>Envie primeiro uma mensagem ao bot desse agente para estabelecer o canal.</p>
            </div>
          </div>
        )}
      </div>

      <footer className="border-t border-border p-3">
        {deliveryWarning && (
          <p className="mb-2 text-xs text-destructive">
            A resposta foi gravada, mas não pôde ser entregue ao Telegram. Atualize o canal antes de tentar novamente.
          </p>
        )}
        {(sendMessage.error || !conversation.data?.session_id) && (
          <p className={cn("mb-2 text-xs", sendMessage.error ? "text-destructive" : "text-muted-foreground")}>
            {sendMessage.error instanceof Error
              ? sendMessage.error.message
              : !conversation.data?.session_id
                ? "A interação fica disponível depois que o bot receber a primeira mensagem no Telegram."
                : null}
          </p>
        )}
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <Textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Conversar com ${agent?.name ?? "o agente"} neste canal…`}
            className="min-h-10 resize-none"
            disabled={!conversation.data?.session_id || sendMessage.isPending}
          />
          <Button
            type="button"
            size="icon"
            onClick={() => void submit()}
            disabled={!draft.trim() || !conversation.data?.session_id || sendMessage.isPending}
            aria-label="Enviar pelo canal Telegram"
          >
            {sendMessage.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </footer>
    </section>
  );
}
