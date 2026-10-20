import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** UI strings for the chat surfaces (assistant greeting, composer
 * placeholder, empty state, attached-context strip), per response
 * language -- keys mirror backend core/config.py's
 * CHAT_RESPONSE_LANGUAGE_NOTES. The hidden per-message instruction makes
 * the AGENT answer in the selected language (see chat.py's
 * _with_language_note); this map keeps the chat's own chrome consistent
 * with it. When adding a language to the backend catalog, add its strings
 * here (and its label to Settings' CHAT_RESPONSE_LANGUAGES). */
export interface ChatUiTexts {
  greeting: string;
  ask: (agentName: string) => string;
  emptyState: (agentName: string) => string;
  contextAttached: string;
}

const CHAT_UI_TEXTS: Record<string, ChatUiTexts> = {
  "pt-BR": {
    greeting: "👋 Sou o assistente do ForgeHub — pergunte qualquer coisa sobre como o sistema funciona.",
    ask: (n) => `Pergunte ao ${n}`,
    emptyState: (n) => `Envie uma mensagem para iniciar a conversa com ${n}.`,
    contextAttached: "📎 Contexto da tela anexado a esta conversa — enviado ao agente de forma invisível.",
  },
  en: {
    greeting: "👋 I'm the ForgeHub assistant — ask me anything about how the system works.",
    ask: (n) => `Ask ${n}`,
    emptyState: (n) => `Send a message to start the conversation with ${n}.`,
    contextAttached: "📎 Screen context attached to this conversation — sent to the agent invisibly.",
  },
  es: {
    greeting: "👋 Soy el asistente de ForgeHub — pregúntame lo que quieras sobre cómo funciona el sistema.",
    ask: (n) => `Pregunta a ${n}`,
    emptyState: (n) => `Envía un mensaje para iniciar la conversación con ${n}.`,
    contextAttached: "📎 Contexto de la pantalla adjunto a esta conversación — enviado al agente de forma invisible.",
  },
  fr: {
    greeting: "👋 Je suis l'assistant ForgeHub — posez-moi vos questions sur le fonctionnement du système.",
    ask: (n) => `Demandez à ${n}`,
    emptyState: (n) => `Envoyez un message pour démarrer la conversation avec ${n}.`,
    contextAttached: "📎 Contexte de l'écran joint à cette conversation — envoyé à l'agent de manière invisible.",
  },
  de: {
    greeting: "👋 Ich bin der ForgeHub-Assistent — frag mich alles darüber, wie das System funktioniert.",
    ask: (n) => `Frag ${n}`,
    emptyState: (n) => `Sende eine Nachricht, um das Gespräch mit ${n} zu beginnen.`,
    contextAttached: "📎 Bildschirmkontext an dieses Gespräch angehängt — wird unsichtbar an den Agenten gesendet.",
  },
  it: {
    greeting: "👋 Sono l'assistente di ForgeHub — chiedimi qualsiasi cosa su come funziona il sistema.",
    ask: (n) => `Chiedi a ${n}`,
    emptyState: (n) => `Invia un messaggio per iniziare la conversazione con ${n}.`,
    contextAttached: "📎 Contesto dello schermo allegato a questa conversazione — inviato all'agente in modo invisibile.",
  },
};

/** Configured chat response language + the matching UI strings. Falls back
 * to English until loaded (or for a language missing from the map), so an
 * unreachable backend degrades to today's default chrome. Saving Settings
 * invalidates ["chat", "language"] (see useUpdateAppConfig), so a language
 * change applies to open chats without a reload. */
export function useChatLanguage(): { language: string; texts: ChatUiTexts } {
  const { data } = useQuery<{ language: string }>({
    queryKey: ["chat", "language"],
    queryFn: () => apiClient.get("/api/v1/chat/language"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const language = data?.language ?? "en";
  return { language, texts: CHAT_UI_TEXTS[language] ?? CHAT_UI_TEXTS.en };
}
