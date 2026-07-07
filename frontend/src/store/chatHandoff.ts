import { create } from "zustand";

/**
 * One-shot handoff for "send to chat" actions elsewhere in the app
 * (Crons/Scripts and Agent Tools pages today): a page composes a draft
 * message, stashes it here, and navigates to /workspace, which consumes it
 * on mount to pre-fill the composer. `agentId` optionally pins which agent
 * the new chat tab should target (e.g. a tool's responsible agent for
 * maintenance) — when absent the workspace falls back to its default.
 * Not persisted -- this is purely an in-memory relay between two route
 * renders in the same session.
 */
export interface ChatHandoff {
  draft: string;
  agentId: string | null;
}

interface ChatHandoffState {
  handoff: ChatHandoff | null;
  setDraft: (draft: string, agentId?: string) => void;
  consumeDraft: () => ChatHandoff | null;
}

export const useChatHandoffStore = create<ChatHandoffState>((set, get) => ({
  handoff: null,
  setDraft: (draft, agentId) => set({ handoff: { draft, agentId: agentId ?? null } }),
  consumeDraft: () => {
    const handoff = get().handoff;
    set({ handoff: null });
    return handoff;
  },
}));
