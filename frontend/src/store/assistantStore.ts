import { create } from "zustand";

/** One field of a form the assistant is allowed to fill (see AssistantForm)
 * -- purely descriptive, the assistant only ever sees this text, it never
 * touches the DOM/React state directly. */
export interface AssistantFormField {
  /** Key used in the forgehub-fill JSON payload, e.g. "subject". */
  name: string;
  /** Human label shown to the agent, e.g. "Subject". */
  label: string;
  /** Free-text hint, e.g. "required", "markdown", "max 255 characters". */
  hint?: string;
}

/** Lets a page opt into the assistant filling its currently-open form on
 * request -- the assistant only ever writes field values via `onFill`
 * (never submits/saves anything itself, see docs/MANUAL.md's Assistant
 * Policy): AssistantDrawer parses a ```forgehub-fill fenced JSON block out
 * of the agent's reply and calls this. */
export interface AssistantForm {
  /** What this form is for, e.g. "New Inbox note". */
  description: string;
  fields: AssistantFormField[];
  onFill: (values: Record<string, string>) => void;
}

/** A page's "Use current X" context for the global Assistant panel --
 * registered via useAssistantContext (src/hooks/useAssistant.ts), read by
 * AssistantDrawer. Whichever page is mounted last wins (there's only ever
 * one active route), and unmounting clears it so a stale builder from a
 * previous page never lingers into the next one. */
export interface AssistantContext {
  /** Label for the "Use current X" button, e.g. "Use current document". */
  label: string;
  /** Builds the context text seeded into the composer -- null means
   * nothing to seed right now (e.g. no document selected yet). */
  build: () => string | null;
  /** cwd for the composer's "!command" prefix, e.g. the current Docs
   * area's host_path. */
  workingDir?: string;
  /** Present only while a fillable form is actually open on screen (e.g.
   * the "New note" dialog) -- absent the rest of the time, so the agent
   * isn't invited to fill a form that isn't there. */
  form?: AssistantForm;
}

interface AssistantState {
  open: boolean;
  setOpen: (open: boolean) => void;
  context: AssistantContext | null;
  setContext: (context: AssistantContext | null) => void;
}

export const useAssistantStore = create<AssistantState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  context: null,
  setContext: (context) => set({ context }),
}));
