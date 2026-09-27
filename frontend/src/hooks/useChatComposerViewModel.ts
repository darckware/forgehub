import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { getAssistantFileDragData, loadAssistantDraggedFile } from "@/lib/assistantFileDrag";

/** ViewModel Hook for ChatPane.tsx's composer -- the second slice of Wave 1's
 * `ChatPane.tsx` split in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`
 * (2026-09-27, Marcelo: "separe o composer do ChatPane em ViewModel e não é
 * um model de formulário"). Owns the draft text, the attachments (and their
 * image previews), the drag-and-drop state, the inline pickers opened while
 * typing (`@` file, `/` command, `#` agent, `$` artifact) and the prompt
 * rewrite dialog.
 *
 * Not a form model: there is no schema and no submit here. The draft is free
 * text, and sending belongs to the still-unextracted send/queue concern, which
 * takes the draft through `takeDraft()` -- so this hook never learns what a
 * send does (local commands, `!bash`, queueing, mentions). Its state machine is
 * `picker`: at most one picker is open at a time, and the keyboard is routed
 * to whichever one it is.
 *
 * Draft and attachments are staged per chat tab in module-level maps rather
 * than only in React state: navigating to another page and back to Workspace
 * remounts the tab's ChatPane from scratch (switching tabs within Workspace
 * just CSS-hides it), so plain useState would lose the pending image/draft; a
 * File can't round-trip through the tabs' localStorage persistence either.
 * These maps survive that remount for the lifetime of the SPA session. */

// Composer auto-grow ceiling -- past this it scrolls internally instead of
// taking over the message area.
export const COMPOSER_MAX_HEIGHT_PX = 240;

const attachmentByTabId = new Map<string, File[]>();
const composerTextByTabId = new Map<string, string>();

/** Drop a closed tab's staged draft/attachments. */
export function clearComposerStaging(tabId: string): void {
  attachmentByTabId.delete(tabId);
  composerTextByTabId.delete(tabId);
}

export type ComposerPicker = "file" | "slash" | "agent" | "artifact";
export type ComposerTrigger = "@" | "/" | "#" | "$" | "!";

export interface PickerState {
  picker: ComposerPicker | null;
  /** What was typed after `#`/`$`; the file and slash pickers filter themselves. */
  query: string;
}

/** Imperative handle every picker exposes, so the textarea keeps focus while
 * the arrow keys and Enter drive the open list. */
export interface ComposerPickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

const TRIGGER_PICKER: Partial<Record<ComposerTrigger, ComposerPicker>> = {
  "@": "file",
  "/": "slash",
  "#": "agent",
  $: "artifact",
};

/** Picker state after the text becomes `value`. A trigger only counts at the
 * start or after whitespace (an e-mail's `@` isn't a mention); `/` only as the
 * whole text. `#`/`$` track what follows them and close at the first space;
 * the file picker stays until something is picked or it's dismissed. */
export function nextPickerState(value: string, prev: PickerState): PickerState {
  const last = value.slice(-1);
  const beforeLast = value.slice(-2, -1);
  const atBoundary = beforeLast === "" || /\s/.test(beforeLast);
  let state = prev;
  if (last === "@" && atBoundary) state = { picker: "file", query: "" };
  if (value === "/") state = { picker: "slash", query: "" };
  else if (state.picker === "slash" && !value.startsWith("/")) state = { picker: null, query: "" };
  for (const [char, picker] of [["#", "agent"], ["$", "artifact"]] as const) {
    if (last === char && atBoundary) {
      state = { picker, query: "" };
    } else if (state.picker === picker) {
      const index = value.lastIndexOf(char);
      const query = index === -1 ? null : value.slice(index + 1);
      state = query === null || /\s/.test(query) ? { picker: null, query: "" } : { picker, query };
    }
  }
  return state;
}

/** `text` with `insert` appended, separated by a space unless it already ends in whitespace. */
function appendWithSpace(text: string, insert: string): string {
  return text + (text.length > 0 && !/\s$/.test(text) ? " " : "") + insert;
}

/** `text` with everything from the last `char` on replaced by `replacement`. */
function replaceFromLast(text: string, char: string, replacement: string): string {
  const index = text.lastIndexOf(char);
  return `${index === -1 ? text : text.slice(0, index)}${replacement}`;
}

export function useChatComposerViewModel(tabId: string, initialText: string | undefined, active: boolean) {
  const { t } = useTranslation("chat");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<ComposerPickerHandle>(null);

  const [text, setText] = useState(() => composerTextByTabId.get(tabId) ?? initialText ?? "");
  useEffect(() => {
    // An empty composer has no draft worth preserving across a remount --
    // and staging "" here would otherwise permanently win over a later
    // initialText (a seed pushed in after this first empty mount), since the
    // lookup above only falls through on null/undefined, not "".
    if (text) composerTextByTabId.set(tabId, text);
    else composerTextByTabId.delete(tabId);
  }, [tabId, text]);

  // Auto-grow with the content -- the single-line height is the floor, and it
  // grows up to COMPOSER_MAX_HEIGHT_PX before scrolling internally. Recompute
  // on `active` too: a tab seeded with a draft while hidden (display:none)
  // measures scrollHeight as 0 until shown.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el || !active) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`;
  }, [text, active]);

  const [files, setFilesState] = useState<File[]>(() => attachmentByTabId.get(tabId) ?? []);
  function updateFiles(update: (current: File[]) => File[]) {
    setFilesState((current) => {
      const next = update(current);
      if (next.length > 0) attachmentByTabId.set(tabId, next);
      else attachmentByTabId.delete(tabId);
      return next;
    });
  }
  const previewUrls = useMemo(
    () => files.map((f) => (f.type.startsWith("image/") ? URL.createObjectURL(f) : null)),
    [files]
  );
  useEffect(() => () => previewUrls.forEach((url) => url && URL.revokeObjectURL(url)), [previewUrls]);

  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  useEffect(() => {
    if (previewIndex === null) return;
    function onKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") setPreviewIndex(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewIndex]);

  const [warning, setWarning] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [pickerState, setPickerState] = useState<PickerState>({ picker: null, query: "" });
  const [improveOpen, setImproveOpen] = useState(false);

  const focus = () => textareaRef.current?.focus();
  const closePicker = () => setPickerState({ picker: null, query: "" });
  const addFiles = (newFiles: File[]) => updateFiles((current) => [...current, ...newFiles]);
  const removeFile = (index: number) => updateFiles((current) => current.filter((_, i) => i !== index));

  /** Replace the whole draft and put the cursor back in it. */
  function replaceText(next: string) {
    setText(next);
    focus();
  }

  /** Insert the picked item in place of what the picker was opened with. */
  function completePicker(update: (current: string) => string) {
    setText(update);
    closePicker();
    focus();
  }

  return {
    textareaRef,
    fileInputRef,
    pickerRef,

    text,
    replaceText,
    /** The textarea's onChange: new text, a stale warning cleared, pickers opened/closed. */
    changeText(value: string) {
      setText(value);
      setWarning(null);
      setPickerState((prev) => nextPickerState(value, prev));
    },
    /** Append after a space, e.g. a dictation transcript. */
    appendText(extra: string) {
      setText((prev) => (prev ? `${prev} ${extra}` : extra));
    },
    /** Put a secret prompt below what's already typed. */
    insertSecret(formattedPrompt: string) {
      setText((current) => {
        const trimmed = current.trim();
        return trimmed.length > 0 ? `${trimmed}\n\n${formattedPrompt}` : formattedPrompt;
      });
      focus();
    },
    /** The attach menu's shortcuts: insert the trigger character as if typed. */
    insertTrigger(char: ComposerTrigger) {
      if (char === "!") {
        // Must be the very first character (a send only runs bash when the
        // text starts with "!") -- prefix, don't append.
        setText((current) => (current.startsWith("!") ? current : `!${current}`));
      } else {
        setText((current) => appendWithSpace(current, char));
        setPickerState({ picker: TRIGGER_PICKER[char] ?? null, query: "" });
      }
      focus();
    },

    /** Hands the draft to a send and empties the composer. */
    takeDraft(): { text: string; files: File[] } {
      const draft = { text, files };
      setText("");
      updateFiles(() => []);
      setWarning(null);
      return draft;
    },
    /** Empties the text only (a local command like "/new" consumed it). */
    clearText() {
      setText("");
      setWarning(null);
    },

    warning,
    setWarning,

    files,
    previewUrls,
    addFiles,
    removeFile,
    openFilePicker: () => fileInputRef.current?.click(),
    pickFiles(e: ChangeEvent<HTMLInputElement>) {
      const picked = Array.from(e.target.files ?? []);
      if (picked.length > 0) addFiles(picked);
      e.target.value = "";
    },
    /** Pasted images become attachments; pasted text is left to the textarea. */
    paste(e: ClipboardEvent<HTMLTextAreaElement>) {
      const imageItems = Array.from(e.clipboardData.items).filter((item) => item.type.startsWith("image/"));
      if (imageItems.length === 0) return;
      e.preventDefault();
      const pasted = imageItems
        .map((item, index) => {
          const file = item.getAsFile();
          if (!file) return null;
          const ext = file.type.split("/")[1] || "png";
          const name =
            file.name && file.name !== "image.png" ? file.name : `pasted-image-${Date.now()}-${index}.${ext}`;
          return new File([file], name, { type: file.type });
        })
        .filter((f): f is File => f !== null);
      if (pasted.length > 0) addFiles(pasted);
    },

    previewIndex,
    openPreview: (index: number) => setPreviewIndex(index),
    closePreview: () => setPreviewIndex(null),
    removePreviewed() {
      if (previewIndex !== null) removeFile(previewIndex);
      setPreviewIndex(null);
    },

    dragActive,
    dragEnter(e: DragEvent<HTMLDivElement>) {
      e.preventDefault();
      setDragActive(true);
    },
    dragOver(e: DragEvent<HTMLDivElement>) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      setDragActive(true);
    },
    dragLeave(e: DragEvent<HTMLDivElement>) {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragActive(false);
    },
    /** A file dragged from the Workspace (Explorer/assistant) is attached, a
     * host folder is referenced by path, OS files are attached, and plain
     * dragged text (a path) is appended. */
    async drop(e: DragEvent<HTMLDivElement>) {
      e.preventDefault();
      setDragActive(false);
      setWarning(null);

      const internalFile = getAssistantFileDragData(e.dataTransfer);
      if (internalFile) {
        if (internalFile.source === "host-folder") {
          setText((current) => {
            const separator = current.length > 0 && !current.endsWith("\n") ? "\n" : "";
            return `${current}${separator}Folder: ${internalFile.path}\n`;
          });
          focus();
          return;
        }
        try {
          addFiles([await loadAssistantDraggedFile(internalFile)]);
          focus();
        } catch {
          setWarning(t("composer.couldNotAttach", { name: internalFile.name }));
        }
        return;
      }

      const droppedFiles = Array.from(e.dataTransfer.files);
      if (droppedFiles.length > 0) {
        addFiles(droppedFiles);
        focus();
        return;
      }

      const path = e.dataTransfer.getData("text/plain");
      if (path) setText((current) => `${appendWithSpace(current, path)} `);
    },

    picker: pickerState.picker,
    pickerQuery: pickerState.query,
    closePicker,
    /** Routes arrows/Enter to the open picker and Esc closes it. Returns true
     * when the key was consumed, so the caller skips its own handling (Enter
     * must pick, not send). */
    handlePickerKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
      if (!pickerState.picker) return false;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        pickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
        return true;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        pickerRef.current?.confirmActive();
        return true;
      }
      if (e.key === "Escape") {
        closePicker();
        return true;
      }
      return false;
    },
    selectFileMention(path: string) {
      completePicker((current) => `${current.endsWith("@") ? current.slice(0, -1) : current}${path} `);
    },
    selectAgentMention(agentName: string) {
      completePicker((current) => replaceFromLast(current, "#", `#${agentName} `));
    },
    selectArtifactMention(path: string) {
      completePicker((current) => replaceFromLast(current, "$", `${path} `));
    },

    improveOpen,
    openImprove: () => setImproveOpen(true),
    closeImprove: () => setImproveOpen(false),
    applyImproved(improved: string) {
      setImproveOpen(false);
      replaceText(improved);
    },
  };
}

export type ChatComposerViewModel = ReturnType<typeof useChatComposerViewModel>;
