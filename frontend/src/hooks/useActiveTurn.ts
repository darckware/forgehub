import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * O turno que está rodando agora, perguntado ao servidor em vez de lembrado
 * pelo navegador (2026-08-13, Marcelo: "não posso perder o contexto e o
 * processamento por um erro ou congelamento do frontend").
 *
 * É o `tmux has-session` do chat. O TerminalPane já resolvia isto há tempos:
 * a sessão vive no host, o id é estável, e reconectar re-anexa. Aqui a
 * pergunta é a mesma -- "há algo rodando nesta sessão, e o que já
 * aconteceu?" -- e a resposta vem do backend, então sobrevive a um F5, a um
 * crash da aba e a abrir em outra máquina.
 *
 * Um hook para as duas superfícies (Marcelo: "um helper para os dois chats
 * conversation e channel"): elas diferem só no `scope`, que decide a rota.
 */

const activeTurnStepSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  label: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
  /** Qual agente executou este passo. Redundante no chat (só um responde) e
   * essencial no canal, onde vários rodam em paralelo -- sem isto os rastros
   * de dois agentes viram uma lista só, sem dono. */
  agent_id: z.string().nullable().optional(),
});

const activeTurnSchema = z.object({
  id: z.string(),
  stream_id: z.string(),
  /** O que o usuário pediu. Vem junto porque, enquanto o turno roda, ainda
   * não existe mensagem persistida a que o balão pendente possa se ancorar. */
  prompt: z.string(),
  agent_id: z.string().nullable(),
  steps: z.array(activeTurnStepSchema).default([]),
  live_text: z.string().default(""),
  /** Só o chat pausa no meio esperando um sim/não. Sem isto, quem reconecta
   * durante a pausa não vê o pedido e o turno espera para sempre. */
  pending_approval: z.record(z.unknown()).nullable().default(null),
  started_at: z.string(),
  deadline_at: z.string().nullable(),
});

export type ActiveTurn = z.infer<typeof activeTurnSchema>;

const responseSchema = z.object({ turn: activeTurnSchema.nullable() });

export type ActiveTurnScope = "chat" | "channel";

function resourceFor(scope: ActiveTurnScope, id: string): string {
  return scope === "chat"
    ? `/api/v1/chat/sessions/${id}/active-turn`
    : `/api/v1/channels/${id}/active-turn`;
}

export const activeTurnKeys = {
  detail: (scope: ActiveTurnScope, id: string) => ["active-turn", scope, id] as const,
};

/**
 * @param scopeId  id da sessão de chat ou do canal; `null` desabilita.
 * @param isBusy   se este cliente já está transmitindo o turno. Quando true,
 *                 o polling para: quem tem o stream aberto recebe tudo ao
 *                 vivo, e consultar seria gastar requisição para saber o que
 *                 já se sabe. O valor continua sendo buscado uma vez na
 *                 montagem, que é justamente o caso de quem acabou de voltar.
 */
export function useActiveTurn(
  scope: ActiveTurnScope,
  scopeId: string | null,
  isBusy = false
) {
  return useQuery({
    queryKey: activeTurnKeys.detail(scope, scopeId ?? ""),
    queryFn: async () =>
      responseSchema.parse(await apiClient.get<unknown>(resourceFor(scope, scopeId!))).turn,
    enabled: Boolean(scopeId),
    // Enquanto há um turno em curso e este cliente não é quem o transmite,
    // pergunta de novo a cada 3s: é o que faz a tela de quem voltou avançar
    // sozinha até o turno terminar. Parado, não pergunta.
    refetchInterval: (query) => (!isBusy && query.state.data ? 3_000 : false),
    // Voltar para a aba é exatamente quando vale reconferir.
    refetchOnWindowFocus: true,
    staleTime: 0,
  });
}
