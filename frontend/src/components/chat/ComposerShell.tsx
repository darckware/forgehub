import { forwardRef, type ChangeEvent, type ClipboardEvent, type CSSProperties, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/**
 * The rounded-pill message composer shell shared by ChatPane
 * (Workspace/Conversas, and AssistantDrawer) and the channel's own
 * composer (ChannelPane) -- factored out (2026-08-06, Marcelo: "ele iria
 * ser fatorado e adiciona as funcionalidades em um só componente" /
 * "tinha pedido que o chat seja igual ao chat de conversa no Workspace")
 * so the two chats can never visually drift apart again, since they now
 * share the exact same container + textarea markup instead of two
 * hand-copied instances of it.
 *
 * Deliberately only the shell (container, textarea, drag-and-drop
 * chrome), not the full composer behavior set (attach menu, @/#/$/!
 * mention pickers, slash commands, voice recording) -- those stay
 * context-specific: ChatPane's are tied to a single agent's ChatSession
 * (file uploads, artifact mentions, voice conversation), while a channel
 * message is multi-author and already has its own #Name mention
 * convention. Forcing those into one shared component would mean a
 * bloated prop surface standing in for behavior that only ever applies to
 * one caller. Callers slot their own buttons/popups in via `leading`
 * (rendered before the textarea, e.g. an attach button + its popups) and
 * `trailing` (after it, e.g. agent pill, mic, voice, send).
 */
export const ComposerShell = forwardRef<
  HTMLTextAreaElement,
  {
    value: string;
    onChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
    onKeyDown?: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
    onPaste?: (e: ClipboardEvent<HTMLTextAreaElement>) => void;
    placeholder?: string;
    leading?: ReactNode;
    trailing?: ReactNode;
    dragActive?: boolean;
    dropHint?: ReactNode;
    onDragEnter?: (e: DragEvent<HTMLDivElement>) => void;
    onDragOver?: (e: DragEvent<HTMLDivElement>) => void;
    onDragLeave?: (e: DragEvent<HTMLDivElement>) => void;
    onDrop?: (e: DragEvent<HTMLDivElement>) => void;
    /** ChatPane's textarea auto-grows (min-h-0, overflow-y-auto, capped
     * via `style.maxHeight`) while the channel's stays a compact
     * single-line default -- both still share the same rounded shell,
     * base textarea classes and padding. Appended to (not replacing) the
     * shared base classes. */
    textareaClassName?: string;
    textareaStyle?: CSSProperties;
  }
>(function ComposerShell(
  {
    value,
    onChange,
    onKeyDown,
    onPaste,
    placeholder,
    leading,
    trailing,
    dragActive,
    dropHint,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
    textareaClassName,
    textareaStyle,
  },
  ref
) {
  return (
    <div
      className={cn(
        "relative flex items-end gap-1 rounded-3xl border bg-muted/50 px-2 py-1.5 transition-colors",
        dragActive ? "border-primary bg-primary/10 ring-2 ring-primary/30" : "border-border"
      )}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {dragActive && dropHint && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-3xl bg-background/90 text-sm font-medium text-primary">
          {dropHint}
        </div>
      )}
      {leading}
      <Textarea
        ref={ref}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        placeholder={placeholder}
        rows={1}
        style={textareaStyle}
        className={cn(
          "min-h-[36px] flex-1 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0",
          textareaClassName
        )}
      />
      {trailing}
    </div>
  );
});
